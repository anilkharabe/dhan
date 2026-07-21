from pymongo import MongoClient
import os
import sys

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), 'backend'))
import config

def purge_database():
    print("⚠️  WARNING: This will PERMANENTLY DELETE all trading history from MongoDB.")
    confirm = input("Are you sure? (type 'yes' to proceed): ")
    
    if confirm.lower() != 'yes':
        print("Purge cancelled.")
        return

    try:
        mongo_uri = getattr(config, 'MONGODB_URI', 'mongodb://localhost:27017/')
        db_name = getattr(config, 'MONGODB_DATABASE', 'nifty_algo_trading')
        
        client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
        db = client[db_name]
        
        # Collections to clear
        collections = [
            'trades', 
            'signals', 
            'performance_stats', 
            'oi_pcr', 
            'system_events',
            'nifty_spot',
            'option_candles'
        ]
        
        print(f"\nPurging database: {db_name}")
        for coll in collections:
            count = db[coll].count_documents({})
            db[coll].delete_many({})
            print(f"  - Cleared '{coll}': {count} documents deleted")
            
        print("\n✅ Database is now clean for a fresh start tomorrow.")
        
        # 2. Clear File System Logs and Charts
        print("\nClearing local file system...")
        
        # Clear logs
        logs_dir = getattr(config, 'LOGS_DIR', '')
        if logs_dir and os.path.exists(logs_dir):
            for f in os.listdir(logs_dir):
                if f.endswith('.log'):
                    os.remove(os.path.join(logs_dir, f))
            print(f"  - Cleared log files in {logs_dir}")
            
        # Clear trade logs
        trade_logs_dir = getattr(config, 'TRADE_LOGS_DIR', '')
        if trade_logs_dir and os.path.exists(trade_logs_dir):
            for f in os.listdir(trade_logs_dir):
                if f.endswith('.xlsx') or f.endswith('.csv'):
                    os.remove(os.path.join(trade_logs_dir, f))
            print(f"  - Cleared trade logs in {trade_logs_dir}")
            
        # Clear charts
        charts_dir = getattr(config, 'CHARTS_DIR', '')
        if charts_dir and os.path.exists(charts_dir):
            import shutil
            for d in os.listdir(charts_dir):
                dir_path = os.path.join(charts_dir, d)
                if os.path.isdir(dir_path):
                    shutil.rmtree(dir_path)
            print(f"  - Cleared chart directories in {charts_dir}")

        print("\n✅ Cleanup complete! Your system is ready for a real trading session.")
        client.close()
        
    except Exception as e:
        print(f"❌ Error purging database: {e}")

if __name__ == "__main__":
    purge_database()
