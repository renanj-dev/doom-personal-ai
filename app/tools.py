from __future__ import annotations
import ast, json, math, operator, platform, re
from dataclasses import dataclass
from typing import Any, Callable
from .models import ToolAuditRecord
from .db import SessionLocal
from .security import PermissionEngine, PermissionMode

_ALLOWED_BINOPS={ast.Add:operator.add,ast.Sub:operator.sub,ast.Mult:operator.mul,ast.Div:operator.truediv,ast.Pow:operator.pow,ast.Mod:operator.mod,ast.FloorDiv:operator.floordiv}
_ALLOWED_UNARY={ast.UAdd:operator.pos,ast.USub:operator.neg}
_ALLOWED_FUNCS={"sqrt":math.sqrt,"abs":abs,"round":round,"sin":math.sin,"cos":math.cos,"tan":math.tan,"log":math.log,"log10":math.log10}
_ALLOWED_NAMES={"pi":math.pi,"e":math.e}

def _eval(node: ast.AST):
    if isinstance(node,ast.Expression): return _eval(node.body)
    if isinstance(node,ast.Constant) and isinstance(node.value,(int,float)): return node.value
    if isinstance(node,ast.BinOp) and type(node.op) in _ALLOWED_BINOPS: return _ALLOWED_BINOPS[type(node.op)](_eval(node.left),_eval(node.right))
    if isinstance(node,ast.UnaryOp) and type(node.op) in _ALLOWED_UNARY: return _ALLOWED_UNARY[type(node.op)](_eval(node.operand))
    if isinstance(node,ast.Name) and node.id in _ALLOWED_NAMES: return _ALLOWED_NAMES[node.id]
    if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id in _ALLOWED_FUNCS:
        if node.keywords: raise ValueError("argumentos nomeados não são permitidos")
        return _ALLOWED_FUNCS[node.func.id](*[_eval(a) for a in node.args])
    raise ValueError("expressão contém uma operação não permitida")

def calculator(expression: str):
    if not expression or len(expression)>200: raise ValueError("expressão vazia ou longa demais")
    value=_eval(ast.parse(expression.strip(),mode="eval"))
    if not math.isfinite(value): raise ValueError("resultado não finito")
    return {"expression":expression.strip(),"result":value}

def current_time():
    from datetime import datetime, timezone
    return {"utc":datetime.now(timezone.utc).isoformat()}

def system_info():
    return {"system":platform.system(),"release":platform.release(),"machine":platform.machine(),"python":platform.python_version()}

@dataclass(frozen=True)
class ToolSpec:
    name:str
    description:str
    handler:Callable[...,Any]
    default_mode:str
    parameters:dict[str,str]

class ToolEngine:
    REQUEST_PREFIX="DOOM_TOOL_REQUEST"
    def __init__(self):
        self.tools:dict[str,ToolSpec]={}
        self.register(ToolSpec("calculator","Calcula expressões matemáticas com um parser seguro.",calculator,PermissionMode.SAFE,{"expression":"string"}))
        self.register(ToolSpec("current_time","Retorna o horário UTC do servidor.",current_time,PermissionMode.SAFE,{}))
        self.register(ToolSpec("system_info","Retorna informações básicas do ambiente do servidor.",system_info,PermissionMode.SAFE,{}))
    def register(self,spec:ToolSpec): self.tools[spec.name]=spec
    def catalog(self):
        return [{"name":x.name,"description":x.description,"permission":x.default_mode,"parameters":x.parameters} for x in self.tools.values()]
    def parse_request(self,text:str):
        text=(text or '').strip()
        if not text: return None
        if text.startswith(self.REQUEST_PREFIX):
            text=text[len(self.REQUEST_PREFIX):].strip()
        if text.startswith('```json') and text.endswith('```'):
            text=text[7:-3].strip()
        try: payload=json.loads(text)
        except Exception: return None
        if not isinstance(payload,dict) or set(payload)!= {'tool','args'} or not isinstance(payload.get('tool'),str) or not isinstance(payload.get('args'),dict): return None
        if payload['tool'] not in self.tools: return {"tool":payload['tool'],"args":payload['args'],"invalid":True}
        return {"tool":payload['tool'].strip(),"args":payload['args'],"invalid":False}
    def execute(self,name:str,args:dict[str,Any],session_id:str,user_id:str|None=None,confirmation_token:str|None=None):
        spec=self.tools.get(name)
        if not spec:
            self._audit(session_id,name,"not_found","blocked",False,"tool_not_found")
            return {"ok":False,"status":"not_found","error":"Ferramenta não encontrada."}
        pe=PermissionEngine()
        decision=pe.authorize(name,session_id,user_id,args,spec.default_mode,confirmation_token)
        self._audit(session_id,name,"authorize",decision["mode"],bool(decision["allowed"]),decision["reason"])
        if not decision["allowed"]: return decision|{"ok":False}
        try: data=spec.handler(**args)
        except Exception as exc:
            self._audit(session_id,name,"execute",decision["mode"],False,str(exc))
            return {"ok":False,"status":"error","error":str(exc)}
        self._audit(session_id,name,"execute",decision["mode"],True,"")
        return {"ok":True,"status":"executed","tool":name,"data":data}
    @staticmethod
    def _audit(session_id,tool,action,permission,ok,detail):
        with SessionLocal() as db:
            db.add(ToolAuditRecord(session_id=session_id,tool=tool,action=action,permission=permission,ok=ok,detail=detail))
            db.commit()

TOOL_ENGINE=ToolEngine()
