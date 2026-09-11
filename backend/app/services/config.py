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


def update_config(db: Session, data) -> SystemConfig:
    """FR3.3 / FR7.5 — Restaurant Manager updates the shared thresholds
    every other module reads via get_or_create_config(). Every module was
    already reading from this table; nothing could ever write to it until
    this existed."""
    config = get_or_create_config(db)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(config, field, value)
    db.commit()
    db.refresh(config)
    return config
