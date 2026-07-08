import os
import re
import uuid
import sqlite3
import psycopg2
import io
from PIL import Image

IMAGE_DIR = "사진"
POSTGRES_URL = "postgresql://my_postgres_db_jeaa_user:xL43VYSA3keTiELFls2VzflbiGsPeeKi@dpg-d92bdla8qa3s73d4hle0-a.oregon-postgres.render.com/my_postgres_db_jeaa"
SQLITE_DB = "live_master.db"
MAX_DIM = 400  # maximum width or height
WEBP_QUALITY = 65

def parse_filename(filename):
    name_part = os.path.splitext(filename)[0]
    match = re.match(r'^(\d+)\s*(.*)$', name_part)
    if match:
        amount = int(match.group(1))
        title = match.group(2).strip() or f"{amount}원 리액션"
        return amount, title
    return None, None

def optimize_image(file_path):
    """
    Resizes the image to have max dimension MAX_DIM and converts to WebP with quality WEBP_QUALITY.
    Returns: webp_bytes, width, height, original_size, optimized_size
    """
    original_size = os.path.getsize(file_path)
    
    with Image.open(file_path) as img:
        # Convert to RGB (to support saving as WebP/JPEG if it's RGBA/PNG)
        if img.mode in ('RGBA', 'LA', 'P'):
            # Keep transparency if it has alpha, but for webp RGBA is fully supported
            pass
        else:
            img = img.convert('RGB')
            
        w, h = img.size
        if max(w, h) > MAX_DIM:
            if w > h:
                new_w = MAX_DIM
                new_h = int(h * (MAX_DIM / w))
            else:
                new_h = MAX_DIM
                new_w = int(w * (MAX_DIM / h))
            img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
            
        out_buf = io.BytesIO()
        # Save as WebP
        img.save(out_buf, format='WEBP', quality=WEBP_QUALITY)
        webp_bytes = out_buf.getvalue()
        optimized_size = len(webp_bytes)
        
        return webp_bytes, img.width, img.height, original_size, optimized_size

def process_postgres(images):
    print("Connecting to PostgreSQL database for optimization...")
    try:
        conn = psycopg2.connect(POSTGRES_URL)
        cursor = conn.cursor()
        print("Connected to PostgreSQL successfully.")
    except Exception as e:
        print(f"PostgreSQL connection error: {e}")
        return

    updated_count = 0
    total_saved_bytes = 0

    for filename, amount, title, file_path in images:
        try:
            # Optimize image to WebP
            webp_bytes, w, h, orig_size, opt_size = optimize_image(file_path)
            saved_bytes = orig_size - opt_size
            total_saved_bytes += saved_bytes
            
            webp_filename = f"{amount}.webp"
            
            # Find the existing item
            cursor.execute("SELECT id, title, image_file_id FROM reaction_items WHERE amount = %s", (amount,))
            rows = cursor.fetchall()
            
            if not rows:
                # If no item exists, skip or we can create it. Let's create it as WebP!
                img_id = f"img_{uuid.uuid4().hex}"
                cursor.execute(
                    "INSERT INTO reaction_files (id, filename, content_type, file_data) VALUES (%s, %s, %s, %s)",
                    (img_id, webp_filename, 'image/webp', psycopg2.Binary(webp_bytes))
                )
                cursor.execute(
                    "INSERT INTO reaction_items (title, amount, image_file_id) VALUES (%s, %s, %s)",
                    (title, amount, img_id)
                )
                print(f"[Postgres] Created '{title}' ({amount}원) as WebP. Size: {orig_size//1024}KB -> {opt_size//1024}KB (-{saved_bytes//1024}KB)")
            else:
                # Update existing items
                for row in rows:
                    item_id, item_title, old_img_id = row
                    
                    img_id = f"img_{uuid.uuid4().hex}"
                    cursor.execute(
                        "INSERT INTO reaction_files (id, filename, content_type, file_data) VALUES (%s, %s, %s, %s)",
                        (img_id, webp_filename, 'image/webp', psycopg2.Binary(webp_bytes))
                    )
                    cursor.execute(
                        "UPDATE reaction_items SET image_file_id = %s WHERE id = %s",
                        (img_id, item_id)
                    )
                    
                    # Delete the old image file if it exists
                    if old_img_id:
                        try:
                            cursor.execute("DELETE FROM reaction_files WHERE id = %s", (old_img_id,))
                        except Exception:
                            pass
                            
                    print(f"[Postgres] Optimized '{item_title}' ({amount}원). Size: {orig_size//1024}KB -> {opt_size//1024}KB (-{saved_bytes//1024}KB)")
                    updated_count += 1
            
            conn.commit()
        except Exception as e:
            conn.rollback()
            print(f"[Postgres Error] Failed to optimize '{filename}': {e}")

    cursor.close()
    conn.close()
    print(f"PostgreSQL Optimization finished. Processed: {updated_count}, Saved bandwidth: {total_saved_bytes//1024//1024}MB")

def process_sqlite(images):
    if not os.path.exists(SQLITE_DB):
        print(f"SQLite DB '{SQLITE_DB}' not found. Skipping SQLite.")
        return

    print("Connecting to local SQLite database for optimization...")
    try:
        conn = sqlite3.connect(SQLITE_DB)
        cursor = conn.cursor()
        print("Connected to SQLite successfully.")
    except Exception as e:
        print(f"SQLite connection error: {e}")
        return

    updated_count = 0
    total_saved_bytes = 0

    for filename, amount, title, file_path in images:
        try:
            # Optimize image to WebP
            webp_bytes, w, h, orig_size, opt_size = optimize_image(file_path)
            saved_bytes = orig_size - opt_size
            total_saved_bytes += saved_bytes
            
            webp_filename = f"{amount}.webp"
            
            # Find the existing item
            cursor.execute("SELECT id, title, image_file_id FROM reaction_items WHERE amount = ?", (amount,))
            rows = cursor.fetchall()
            
            if not rows:
                img_id = f"img_{uuid.uuid4().hex}"
                cursor.execute(
                    "INSERT INTO reaction_files (id, filename, content_type, file_data) VALUES (?, ?, ?, ?)",
                    (img_id, webp_filename, 'image/webp', webp_bytes)
                )
                cursor.execute(
                    "INSERT INTO reaction_items (title, amount, image_file_id) VALUES (?, ?, ?)",
                    (title, amount, img_id)
                )
                print(f"[SQLite] Created '{title}' ({amount}원) as WebP. Size: {orig_size//1024}KB -> {opt_size//1024}KB (-{saved_bytes//1024}KB)")
            else:
                # Update existing items
                for row in rows:
                    item_id, item_title, old_img_id = row
                    
                    img_id = f"img_{uuid.uuid4().hex}"
                    cursor.execute(
                        "INSERT INTO reaction_files (id, filename, content_type, file_data) VALUES (?, ?, ?, ?)",
                        (img_id, webp_filename, 'image/webp', webp_bytes)
                    )
                    cursor.execute(
                        "UPDATE reaction_items SET image_file_id = ? WHERE id = ?",
                        (img_id, item_id)
                    )
                    
                    if old_img_id:
                        try:
                            cursor.execute("DELETE FROM reaction_files WHERE id = ?", (old_img_id,))
                        except Exception:
                            pass
                            
                    print(f"[SQLite] Optimized '{item_title}' ({amount}원). Size: {orig_size//1024}KB -> {opt_size//1024}KB (-{saved_bytes//1024}KB)")
                    updated_count += 1
            
            conn.commit()
        except Exception as e:
            conn.rollback()
            print(f"[SQLite Error] Failed to optimize '{filename}': {e}")

    cursor.close()
    conn.close()
    print(f"SQLite Optimization finished. Processed: {updated_count}, Saved bandwidth: {total_saved_bytes//1024//1024}MB")

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

    print(f"Found {len(images)} image assets for optimization.")
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
