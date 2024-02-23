import asyncio

from app.lib.worker import CidrWorker

if __name__ == "__main__":
    print("Starting...")
    cidr_worker = CidrWorker()
    asyncio.run(cidr_worker.run())
    print("Finished...")
