import os
import shutil

def copy_and_rename_files(src_file, dest_dir, num_copies):
    # Ensure the destination directory exists
    if not os.path.exists(dest_dir):
        os.makedirs(dest_dir)

    # Copy and rename files
    for i in range(1, num_copies + 1):
        dest_file = os.path.join(dest_dir, f'manyportfolios{i}.csv')
        shutil.copy2(src_file, dest_file)
        print(f'Copied {src_file} to {dest_file}')

if __name__ == "__main__":
    src_file = 'BASE_PATH/refdata/manyportfolios.csv'
    dest_dir = 'BASE_PATH/refdata/pooltest'
    num_copies = 20000

    copy_and_rename_files(src_file, dest_dir, num_copies)
