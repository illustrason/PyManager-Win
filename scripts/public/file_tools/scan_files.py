import os


def list_files_in_directory(directory_path, output_file, show_tree=False):
    """
    List every file in a folder and write the result to a text file.

    Args:
        directory_path (str): Folder to scan.
        output_file (str): Path of the output text file.
        show_tree (bool): Whether to show the folder tree (indented) or a flat list.
    """
    try:
        # Make sure the folder exists
        if not os.path.exists(directory_path):
            print(f"The specified folder does not exist: {directory_path}")
            return

        # Create the output folder if needed
        output_dir = os.path.dirname(output_file)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir)

        # Write the list of files
        with open(output_file, 'w', encoding='utf-8') as f:
            for root, dirs, files in os.walk(directory_path):
                if show_tree:
                    # Write the folder name, indented by its depth
                    indent_level = root.replace(directory_path, "").count(os.sep)
                    indent = "    " * indent_level
                    f.write(f"{indent}[{os.path.basename(root)}]\n")
                for file in files:
                    indent = "    " * (indent_level + 1) if show_tree else ""
                    f.write(f"{indent}{file}\n")

        print(f"File list written to: {output_file}")

    except Exception as e:
        print(f"An error occurred: {e}")


# Parameters
directory_to_scan = "input"  # folder to scan @expose
output_file_path = "output/file_list.txt"  # output text file @expose
show_tree = True  # show the folder tree? @expose

list_files_in_directory(directory_to_scan, output_file_path, show_tree)
