from service.lib.request_deposit_helper import request_deposit, request_deposit_for_csv

if __name__ == '__main__':
    if len(sys.argv) != 3:
        print('Usage: service/scripts/request_deposits_from_csv.py <repository_id> <notification_ids_csv_file>\n CSV file has to have column <notification_id>.')
        exit()

    repository_id = sys.argv[1]
    csv_file = sys.argv[2]
    if not os.path.isfile(csv_file):
        print(f"file does not exist {csv_file}")
        exit()
    print(f"Starting creating deposit requests for {repository_id}")
    total_count, count, duplicate = request_deposit_for_csv(repository_id, csv_file)
    print(f"{total_count} notifications requested to be queued for deposit")
    print(f"{count} notifications queued for deposit")
    print(f"{duplicate} notifications are already waiting in queue")
    print(f"Done creating deposit requests for {repository_id}")