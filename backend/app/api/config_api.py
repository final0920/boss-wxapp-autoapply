"""config_api — 画像/规则/阈值/限速 CRUD（鉴权 AC12）。"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import ValidationError
from sqlmodel import Session, select

from app.config import settings
from app.db import get_db
from app.models import Config
from app.rules import RulesConfig, load_rules, save_rules
from app.security.auth import require_auth

router = APIRouter(prefix="/config", tags=["config"])


@router.get("", dependencies=[Depends(require_auth)])
async def list_config(db: Session = Depends(get_db)) -> list[dict]:
    items = db.exec(select(Config)).all()
    return [{"key": c.key, "value": c.value, "updated_at": c.updated_at.isoformat()} for c in items]


@router.get("/model-info", dependencies=[Depends(require_auth)])
async def get_model_info() -> dict:
    """模型只读信息（model/base_url/reasoning），供设置页展示。

    不含 API Key —— Key 仅后端持有，从 .env 注入。
    注意：此路由必须注册在 /{key} 之前，否则 'model-info' 会被当作 key 匹配。
    """
    return {
        "model": settings.gpt_model,
        "base_url": settings.gpt_base_url,
        "reasoning": settings.gpt_reasoning,
    }


@router.get("/rules", dependencies=[Depends(require_auth)])
async def get_rules(db: Session = Depends(get_db)) -> dict:
    """返回完整 RulesConfig JSON。注册在 /{key} 之前，防止路由遮蔽。"""
    rules = load_rules(db)
    return rules.model_dump()


@router.put("/rules", dependencies=[Depends(require_auth)])
async def set_rules(body: dict, db: Session = Depends(get_db)) -> dict:
    """全量写入 RulesConfig。body 经 extra='forbid' 校验，未知字段自动 422。"""
    try:
        rules = RulesConfig.model_validate(body)
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=exc.errors())
    save_rules(db, rules)
    return rules.model_dump()


@router.get("/{key}", dependencies=[Depends(require_auth)])
async def get_config(key: str, db: Session = Depends(get_db)) -> dict:
    c = db.exec(select(Config).where(Config.key == key)).first()
    if c is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Config key '{key}' not found")
    return {"key": c.key, "value": c.value, "updated_at": c.updated_at.isoformat()}


@router.put("/{key}", dependencies=[Depends(require_auth)])
async def set_config(key: str, body: dict, db: Session = Depends(get_db)) -> dict:
    value = str(body.get("value", ""))
    c = db.exec(select(Config).where(Config.key == key)).first()
    if c is None:
        c = Config(key=key, value=value, updated_at=datetime.now())
        db.add(c)
    else:
        c.value = value
        c.updated_at = datetime.now()
        db.add(c)
    db.commit()
    db.refresh(c)
    return {"key": c.key, "value": c.value, "updated_at": c.updated_at.isoformat()}


@router.delete("/{key}", dependencies=[Depends(require_auth)])
async def delete_config(key: str, db: Session = Depends(get_db)) -> dict:
    c = db.exec(select(Config).where(Config.key == key)).first()
    if c is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Config key '{key}' not found")
    db.delete(c)
    db.commit()
    return {"deleted": key}
