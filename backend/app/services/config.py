"""Shared Configuration accessor. SystemConfig is a single-row table (Ch4
§4.3.1); this lazily creates that row with defaults on first access rather
than requiring a migration data-seed step."""
from sqlalchemy.orm import Session

from app.models.config import SystemConfig


def get_or_create_config(db: Session) -> SystemConfig:
    config = db.query(SystemConfig).first()
    if config is None:
        config = SystemConfig()
        db.add(config)
        db.commit()
        db.refresh(config)
    return config
