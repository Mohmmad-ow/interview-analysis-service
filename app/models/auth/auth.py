from enum import Enum
from typing import Optional, List
from pydantic import BaseModel


class UserTier(str, Enum):
    STANDARD = "standard"
    PREMIUM = "premium"
    ADMIN = "admin"


class UserContext(BaseModel):
    user_id: str
    tier: UserTier
    email: Optional[str] = None
    permissions: List[str] = []

    @property
    def is_admin(self) -> bool:
        return self.tier == UserTier.ADMIN

    @property
    def is_premium(self) -> bool:
        return self.tier in [UserTier.ADMIN, UserTier.PREMIUM]

    def has_permissions(self, permission: str) -> bool:
        return permission in self.permissions
