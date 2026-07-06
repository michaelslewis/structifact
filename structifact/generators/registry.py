from .sql import SQLGenerator
from .dbt_yaml import DBTYAMLGenerator

GENERATORS = [
    SQLGenerator(),
    DBTYAMLGenerator(),
]