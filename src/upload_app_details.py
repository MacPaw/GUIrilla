import argparse
import os

google_cloud_storage = "gs://ai-lab/datasets/never-ending-learning-artifacts"

def is_cloud_path_exists(path):
    try:
        print(f"Checking if cloud path exists: {path}")
        return os.system(f'gsutil ls "{path}"') == 0
    except:
        return False

def upload_folder_to_cloud(path, cloud_folder):
    print(f'Uploading "{path}" to "{cloud_folder}"')

    if not os.path.exists(path):
        print("Folder does not exist")
        return
    
    base_folder_name = os.path.split(path)[-1]
    for subpath in os.listdir(path):
        full_local_path = os.path.join(path, subpath)
        container_path = os.path.join(cloud_folder, base_folder_name)
        destination_path = os.path.join(container_path, subpath)
        if os.path.isdir(full_local_path):    
            if is_cloud_path_exists(destination_path):
                print(f"Folder {destination_path} already exists, skip uploading")
                continue
            result = os.system(f'gcloud storage cp "{full_local_path}" "{destination_path}" --recursive -n --continue-on-error')
            if result == 0:
                print("Uploaded path to the cloud")
            else:
                print("Failed to upload archive to the cloud")


if __name__ == "__main__":
    arg_parser = argparse.ArgumentParser(description="Parse -i argument")

    arg_parser.add_argument("-i", type=str, help="Input file")
    args = arg_parser.parse_args()

    input_path = args.i

    print(f"Input path: {input_path}")

    # upload the app details to the server
    print("----------------------------------------------")
    print("Uploading app details to the server...")

    upload_folder_to_cloud(input_path, google_cloud_storage)


