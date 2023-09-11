- Migrations should be created as individual SQL files in `./sql` using a transaction  
- The name of the migration must start with a number then an underscore (`_`), after that anything is valid  
- Pad the numbers with leading zeros and be consistent, use always 2 or 3 or four digits but don't mix  
- Migrations will be executed in numeric order  

Example:

```
./sql/00_create_tables.sql
./sql/01_triggers.sql
./sql/02_insert_default_data.sql
```
