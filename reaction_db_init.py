import psycopg2
import sys

db_url = 'postgresql://my_postgres_db_jeaa_user:xL43VYSA3keTiELFls2VzflbiGsPeeKi@dpg-d92bdla8qa3s73d4hle0-a.oregon-postgres.render.com/my_postgres_db_jeaa'

def init_tables():
    print("Connecting to remote PostgreSQL database to create reaction tables...")
    try:
        conn = psycopg2.connect(db_url)
        cursor = conn.cursor()
        
        # 1. Create reaction_files table
        print("Creating table: reaction_files...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS reaction_files (
                id VARCHAR(64) PRIMARY KEY,
                filename TEXT NOT NULL,
                content_type VARCHAR(128) NOT NULL,
                file_data BYTEA NOT NULL
            )
        """)
        
        # 2. Create reaction_items table
        print("Creating table: reaction_items...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS reaction_items (
                id SERIAL PRIMARY KEY,
                title TEXT NOT NULL,
                amount INTEGER DEFAULT 0,
                audio_file_id VARCHAR(64) REFERENCES reaction_files(id) ON DELETE SET NULL,
                image_file_id VARCHAR(64) REFERENCES reaction_files(id) ON DELETE SET NULL
            )
        """)
        
        conn.commit()
        print("Tables created successfully!")
        cursor.close()
        conn.close()
    except Exception as e:
        print("Error creating tables:", e)
        sys.exit(1)

if __name__ == '__main__':
    init_tables()
