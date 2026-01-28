"""
Database module for storing projections in PostgreSQL
Works with Render's PostgreSQL database
"""
import os
import json
import psycopg2
from psycopg2.extras import Json
from datetime import datetime

class ProjectionDB:
    def __init__(self):
        self.database_url = os.environ.get('DATABASE_URL')
        if self.database_url:
            # Render uses postgres:// but psycopg2 needs postgresql://
            if self.database_url.startswith('postgres://'):
                self.database_url = self.database_url.replace('postgres://', 'postgresql://', 1)
            self.init_db()
        else:
            print("⚠️  No DATABASE_URL found - projections won't persist across devices")
    
    def get_connection(self):
        """Get database connection"""
        if not self.database_url:
            return None
        try:
            return psycopg2.connect(self.database_url)
        except Exception as e:
            print(f"❌ Database connection error: {e}")
            return None
    
    def init_db(self):
        """Initialize database table"""
        conn = self.get_connection()
        if not conn:
            return
        
        try:
            cur = conn.cursor()
            
            # Create projections table if it doesn't exist
            cur.execute("""
                CREATE TABLE IF NOT EXISTS projections (
                    id SERIAL PRIMARY KEY,
                    projections JSONB NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Check if we have any rows
            cur.execute("SELECT COUNT(*) FROM projections")
            count = cur.fetchone()[0]
            
            # If no rows, insert a placeholder
            if count == 0:
                cur.execute("""
                    INSERT INTO projections (projections)
                    VALUES (%s)
                """, (Json([]),))
            
            conn.commit()
            print("✅ Database initialized successfully")
            
        except Exception as e:
            print(f"❌ Database init error: {e}")
            conn.rollback()
        finally:
            cur.close()
            conn.close()
    
    def save_projections(self, projections):
        """Save projections to database"""
        conn = self.get_connection()
        if not conn:
            print("⚠️  No database connection - using in-memory only")
            return False
        
        try:
            cur = conn.cursor()
            
            # Update the first (and only) row
            cur.execute("""
                UPDATE projections 
                SET projections = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = 1
            """, (Json(projections),))
            
            # If no row was updated, insert one
            if cur.rowcount == 0:
                cur.execute("""
                    INSERT INTO projections (id, projections)
                    VALUES (1, %s)
                    ON CONFLICT (id) DO UPDATE 
                    SET projections = EXCLUDED.projections,
                        updated_at = CURRENT_TIMESTAMP
                """, (Json(projections),))
            
            conn.commit()
            print(f"💾 Saved {len(projections)} projections to database")
            return True
            
        except Exception as e:
            print(f"❌ Database save error: {e}")
            conn.rollback()
            return False
        finally:
            cur.close()
            conn.close()
    
    def load_projections(self):
        """Load projections from database"""
        conn = self.get_connection()
        if not conn:
            print("⚠️  No database connection - returning empty projections")
            return []
        
        try:
            cur = conn.cursor()
            
            cur.execute("""
                SELECT projections, updated_at 
                FROM projections 
                WHERE id = 1
            """)
            
            row = cur.fetchone()
            if row:
                projections = row[0]
                updated_at = row[1]
                if projections and len(projections) > 0:
                    print(f"📂 Loaded {len(projections)} projections from database (updated: {updated_at})")
                    return projections
                else:
                    print("ℹ️  Database has no projections")
                    return []
            else:
                print("ℹ️  No projections found in database")
                return []
            
        except Exception as e:
            print(f"❌ Database load error: {e}")
            return []
        finally:
            cur.close()
            conn.close()
