import os

# Parameters
base_name = "file_name_"  # base name; a number and the original extension are appended @expose
directory_path = "input"  # folder containing the files to rename @expose


def rename_files_in_directory(directory, base_name):
    # List everything in the folder
    files = os.listdir(directory)

    # Sort so the files are numbered in a predictable order
    files.sort()

    # Rename each file in turn
    for i, filename in enumerate(files, start=1):
        # Keep the original extension
        file_extension = os.path.splitext(filename)[1]

        # Build the new name with a zero-padded counter
        new_name = f"{base_name}{i:02}{file_extension}"

        # Full paths of the old and new files
        old_file = os.path.join(directory, filename)
        new_file = os.path.join(directory, new_name)

        # Rename the file
        os.rename(old_file, new_file)
        print(f"Renamed '{old_file}' to '{new_file}'")


rename_files_in_directory(directory_path, base_name)
