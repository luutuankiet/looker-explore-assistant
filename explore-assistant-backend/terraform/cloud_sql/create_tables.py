from database import create_db_and_tables, get_database_url, engine
import sys
import os
import json
from sqlmodel import SQLModel, inspect

# Add the root directory to the Python path
root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..'))

# Import models from cloud-run directory
sys.path.insert(0, os.path.join(root_dir, 'explore-assistant-cloud-run'))

# this will now import the foreign models table from cloud run folder
import models

def get_table_info():
    """Extract information about all tables defined in SQLModel metadata"""
    inspector = inspect(engine)
    table_names = inspector.get_table_names()
    
    tables_info = {}
    for table_name in table_names:
        columns = inspector.get_columns(table_name)
        tables_info[table_name] = {
            "columns": [
                {
                    "name": column["name"],
                    "type": str(column["type"]),
                    "nullable": column.get("nullable", True),
                    "default": str(column.get("default", "None")),
                    "primary_key": column.get("primary_key", False)
                }
                for column in columns
            ]
        }
    
    return tables_info

def main():
    print("Creating database and tables...")
    print(f"Using database URL: {get_database_url()}")
    create_db_and_tables()
    print("Tables created successfully!")
    
    # save a simple list of tables for Terraform to use
    table_names = list(get_table_info().keys())
    with open(os.path.join(os.path.dirname(__file__), "table_names.json"), "w") as f:
        json.dump({"tables": table_names}, f)

if __name__ == "__main__":
    main()
