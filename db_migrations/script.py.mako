"""A generic single-database configuration."""

from typing import Any

revision: str = ${repr(up_revision)}
down_revision: Any = ${repr(down_revision)}
branch_labels: Any = ${repr(branch_labels)}
depends_on: Any = ${repr(depends_on)}

