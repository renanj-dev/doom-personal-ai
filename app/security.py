from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
import hashlib, hmac, json, secrets
from sqlalchemy import select
from .db import SessionLocal
from .models import ToolPermission, ToolConfirmation

class PermissionMode:
    SAFE='safe'; CONFIRM='confirm'; BLOCKED='blocked'

@dataclass(frozen=True)
class Decision:
    allowed: bool; requires_confirmation: bool; mode: str; source: str; reason: str


def _hash_args(args:dict) -> str:
    return hashlib.sha256(json.dumps(args or {},sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()

def _hash_token(token:str)->str: return hashlib.sha256(token.encode()).hexdigest()

class PermissionEngine:
    def authorize(self, tool:str, session_id:str, user_id:str|None, args:dict, default_mode:str, token:str|None=None):
        mode=default_mode; source='default'
        with SessionLocal() as db:
            for scope, scope_id in [('session',session_id),('user',user_id),('global',None)]:
                if scope=='user' and not user_id: continue
                row=db.scalar(select(ToolPermission).where(ToolPermission.tool_name==tool,ToolPermission.scope==scope,ToolPermission.scope_id==scope_id))
                if row:
                    source=scope
                    if not row.enabled: mode=PermissionMode.BLOCKED
                    else: mode=row.mode
                    break
            if mode==PermissionMode.BLOCKED:
                return {'allowed':False,'requires_confirmation':False,'mode':mode,'source':source,'reason':'blocked_by_policy'}
            if mode==PermissionMode.SAFE:
                return {'allowed':True,'requires_confirmation':False,'mode':mode,'source':source,'reason':'safe'}
            if not token:
                raw=secrets.token_urlsafe(32); now=datetime.now(timezone.utc)
                db.add(ToolConfirmation(token_hash=_hash_token(raw),session_id=session_id,user_id=user_id,tool_name=tool,args_hash=_hash_args(args),created_at=now,expires_at=now+timedelta(seconds=120)))
                db.commit()
                return {'allowed':False,'requires_confirmation':True,'mode':mode,'source':source,'reason':'confirmation_required','confirmation_token':raw,'expires_in':120}
            row=db.scalar(select(ToolConfirmation).where(ToolConfirmation.token_hash==_hash_token(token)))
            now=datetime.now(timezone.utc)
            if not row: return {'allowed':False,'requires_confirmation':False,'mode':mode,'source':source,'reason':'invalid_confirmation'}
            exp=row.expires_at.replace(tzinfo=timezone.utc) if row.expires_at.tzinfo is None else row.expires_at
            if row.used_at is not None: return {'allowed':False,'requires_confirmation':False,'mode':mode,'source':source,'reason':'confirmation_already_used'}
            if exp<=now: return {'allowed':False,'requires_confirmation':False,'mode':mode,'source':source,'reason':'confirmation_expired'}
            if row.session_id!=session_id or row.user_id!=user_id or row.tool_name!=tool or not hmac.compare_digest(row.args_hash,_hash_args(args)):
                return {'allowed':False,'requires_confirmation':False,'mode':mode,'source':source,'reason':'confirmation_mismatch'}
            row.used_at=now; db.commit()
            return {'allowed':True,'requires_confirmation':False,'mode':mode,'source':source,'reason':'confirmation_consumed'}
