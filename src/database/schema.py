# Database/schema.py

from dataclasses import dataclass, field
from typing import List


@dataclass
class Column:
    name: str
    data_type: str
    is_primary_key: bool = False

    def __str__(self):
        pk_indicator = " (PK)" if self.is_primary_key else ""
        return f"{self.name} {self.data_type}{pk_indicator}"


@dataclass
class ForeignKey:
    name: str
    parent_table: str
    referenced_table: str


@dataclass
class Table:
    name: str
    columns: List[Column] = field(default_factory=list)
    foreign_keys: List[ForeignKey] = field(default_factory=list)

    def __str__(self):
        columns_str = ", ".join(str(column) for column in self.columns)
        fks_str = ", ".join(
            f"{fk.name} -> {fk.referenced_table}" for fk in self.foreign_keys
        )
        fks_indicator = f" | Foreign Keys: [{fks_str}]" if fks_str != "" else ""
        return f"Table: {self.name} | Columns: [{columns_str}]{fks_indicator}"


@dataclass
class DatabaseSchema:
    tables: List[Table] = field(default_factory=list)

    def __str__(self):
        return "\n".join(str(table) for table in self.tables)
