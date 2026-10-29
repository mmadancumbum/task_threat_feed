"""Create only the configured database and initial tables; never reset existing data."""
from sqlalchemy import create_engine, text
from app.db import engine, Base

if __name__ == '__main__':
    name = engine.url.database
    if not name or not name.replace('_', '').isalnum():
        raise SystemExit('Use an alphanumeric/underscore database name.')
    server = create_engine(engine.url._replace(database=None), isolation_level='AUTOCOMMIT')
    with server.connect() as connection:
        connection.execute(text(f'CREATE DATABASE IF NOT EXISTS `{name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_bin'))
    Base.metadata.create_all(engine)
    print(f'Database {name} is ready.')
