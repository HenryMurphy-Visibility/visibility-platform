import subprocess

def dispatch():
    # Example dispatch logic, you may add more complex logic as needed
    processes = [
        subprocess.Popen(["python", "chest_s1/shard_server.py", "chest_s1"]),
        subprocess.Popen(["python", "chest_s2/shard_server.py", "chest_s2"])
    ]

    for p in processes:
        p.wait()

if __name__ == "__main__":
    dispatch()


