import logging


class Shard:
    def __init__(self, name, current_period_data, process_domain_events, cpu_core):
        self.name = name
        self.current_period_data = current_period_data
        self.process_domain_events = process_domain_events
        self.cpu_core = cpu_core
        self.portfolios = []
        self.processing_times = []

    def add_portfolio(self, portfolio_file):
        self.portfolios.append(portfolio_file)

    def start(self):
        # Here you would implement the logic to start processing in the shard
        logging.info(f"Shard {self.name} is starting on CPU core {self.cpu_core}")

    def join(self):
        # Here you would implement the logic to wait for the shard process to complete
        logging.info(f"Shard {self.name} has completed processing")

def add_shard(shards, name, current_period_data, process_domain_events, cpu_core):
    shard = Shard(name, current_period_data, process_domain_events, cpu_core)
    shards.append(shard)
