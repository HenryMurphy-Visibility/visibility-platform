import sys
from sharding import Shard, GlobalViewCoordinator, assign_portfolios_to_shards, add_shard
import threading

def main(shard_name):
    # Initialize the shard and start processing
    shard = Shard(shard_id=0, name=shard_name)
    gvc = GlobalViewCoordinator()

    # Start the GVC in a separate thread
    gvc_thread = threading.Thread(target=gvc.start, args=([shard],))
    gvc_thread.start()

    # Start the shard in a separate thread
    processing_thread = threading.Thread(target=shard.run)
    processing_thread.start()

    # Example portfolio list with assigned shard
    portfolios = [
        {'portfolio_id': "MyPortfolio", 'shard_name': shard_name, 'event_type': 'update', 'data': 'data1'}
    ]

    # Assign portfolios to the shard
    assign_portfolios_to_shards(portfolios, [shard])

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python shard_server.py <shard_name>")
        sys.exit(1)

    shard_name = sys.argv[1]
    main(shard_name)
