import os
import re
import uuid
import sqlite3
import psycopg2

IMAGE_DIR = "사진"
POSTGRES_URL = "postgresql://my_postgres_db_jeaa_user:xL43VYSA3keTiELFls2VzflbiGsPeeKi@dpg-d92bdla8qa3s73d4hle0-a.oregon-postgres.render.com/my_postgres_db_jeaa"
SQLITE_DB = "live_master.db"

def get_content_type(filename):
    ext = os.path.splitext(filename.lower())[1]
    if ext == '.gif':
        return 'image/gif'
    elif ext in ['.jpg', '.jpeg']:
        return 'image/jpeg'
    elif ext == '.webp':
        return 'image/webp'
    return 'image/png'

def parse_filename(filename):
    # Matches digits at start, followed by optional name
    name_part = os.path.splitext(filename)[0]
    match = re.match(r'^(\d+)\s*(.*)$', name_part)
    if match:
        amount = int(match.group(1))
        title = match.group(2).strip() or f"{amount}원 리액션"
        return amount, title
    return None, None

def process_postgres(images):
    print("Connecting to PostgreSQL database...")
    try:
        conn = psycopg2.connect(POSTGRES_URL)
        cursor = conn.cursor()
        print("Connected to PostgreSQL successfully.")
    except Exception as e:
        print(f"PostgreSQL connection error: {e}")
        return

    updated_count = 0
    created_count = 0

    for filename, amount, title, file_path in images:
        try:
            with open(file_path, 'rb') as f:
                img_data = f.read()

            content_type = get_content_type(filename)
            
            # Check if reaction item already exists for this amount
            cursor.execute("SELECT id, title, image_file_id FROM reaction_items WHERE amount = %s", (amount,))
            rows = cursor.fetchall()
            
            img_id = f"img_{uuid.uuid4().hex}"
            # Insert image file
            cursor.execute(
                "INSERT INTO reaction_files (id, filename, content_type, file_data) VALUES (%s, %s, %s, %s)",
                (img_id, filename, content_type, psycopg2.Binary(img_data))
            )

            if rows:
                # Update existing items
                for row in rows:
                    item_id, item_title, old_img_id = row
                    cursor.execute(
                        "UPDATE reaction_items SET image_file_id = %s WHERE id = %s",
                        (img_id, item_id)
                    )
                    if old_img_id:
                        try:
                            cursor.execute("DELETE FROM reaction_files WHERE id = %s", (old_img_id,))
                        except Exception:
                            pass
                    print(f"[Postgres] Updated item '{item_title}' ({amount}원) with image '{filename}'")
                    updated_count += 1
            else:
                # Create a new item
                cursor.execute(
                    "INSERT INTO reaction_items (title, amount, image_file_id) VALUES (%s, %s, %s)",
                    (title, amount, img_id)
                )
                print(f"[Postgres] Created new item '{title}' ({amount}원) with image '{filename}'")
                created_count += 1

            conn.commit()
        except Exception as e:
            conn.rollback()
            print(f"[Postgres Error] Failed to process '{filename}': {e}")

    cursor.close()
    conn.close()
    print(f"PostgreSQL processing finished. Updated: {updated_count}, Created: {created_count}")

def process_sqlite(images):
    if not os.path.exists(SQLITE_DB):
        print(f"SQLite DB '{SQLITE_DB}' not found. Skipping SQLite.")
        return

    print("Connecting to local SQLite database...")
    try:
        conn = sqlite3.connect(SQLITE_DB)
        cursor = conn.cursor()
        print("Connected to SQLite successfully.")
    except Exception as e:
        print(f"SQLite connection error: {e}")
        return

    updated_count = 0
    created_count = 0

    for filename, amount, title, file_path in images:
        try:
            with open(file_path, 'rb') as f:
                img_data = f.read()

            content_type = get_content_type(filename)
            
            # Check if reaction item already exists for this amount
            cursor.execute("SELECT id, title, image_file_id FROM reaction_items WHERE amount = ?", (amount,))
            rows = cursor.fetchall()
            
            img_id = f"img_{uuid.uuid4().hex}"
            # Insert image file
            cursor.execute(
                "INSERT INTO reaction_files (id, filename, content_type, file_data) VALUES (?, ?, ?, ?)",
                (img_id, filename, content_type, img_data)
            )

            if rows:
                # Update existing items
                for row in rows:
                    item_id, item_title, old_img_id = row
                    cursor.execute(
                        "UPDATE reaction_items SET image_file_id = ? WHERE id = ?",
                        (img_id, item_id)
                    )
                    if old_img_id:
                        try:
                            cursor.execute("DELETE FROM reaction_files WHERE id = ?", (old_img_id,))
                        except Exception:
                            pass
                    print(f"[SQLite] Updated item '{item_title}' ({amount}원) with image '{filename}'")
                    updated_count += 1
            else:
                # Create a new item
                cursor.execute(
                    "INSERT INTO reaction_items (title, amount, image_file_id) VALUES (?, ?, ?)",
                    (title, amount, img_id)
                )
                print(f"[SQLite] Created new item '{title}' ({amount}원) with image '{filename}'")
                created_count += 1

            conn.commit()
        except Exception as e:
            conn.rollback()
            print(f"[SQLite Error] Failed to process '{filename}': {e}")

    cursor.close()
    conn.close()
    print(f"SQLite processing finished. Updated: {updated_count}, Created: {created_count}")

def main():
    if not os.path.exists(IMAGE_DIR):
        print(f"Error: Folder '{IMAGE_DIR}' does not exist.")
        return

    files = os.listdir(IMAGE_DIR)
    images = []
    
    for filename in files:
        file_path = os.path.join(IMAGE_DIR, filename)
        if os.path.isdir(file_path):
            continue
        
        amount, title = parse_filename(filename)
        if amount is not None:
            images.append((filename, amount, title, file_path))

    print(f"Found {len(images)} valid image assets in '{IMAGE_DIR}' folder.")
    if not images:
        print("No images to process.")
        return

    # Process PostgreSQL first
    process_postgres(images)
    print("-" * 50)
    # Process SQLite second
    process_sqlite(images)

if __name__ == "__main__":
    main()
