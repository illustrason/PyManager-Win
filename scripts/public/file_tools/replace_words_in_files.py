import os

# Parameters
old_word = 'oldWord'  # text to replace in file and folder names @expose
new_word = 'newWord'  # replacement text @expose
directory_path = 'input'  # folder to process (searched recursively) @expose


def rename_recursively(root_dir, old_word, new_word):
    # Walk bottom-up so folders are renamed after the items they contain
    for current_path, dirnames, filenames in os.walk(root_dir, topdown=False):
        # Rename files
        for filename in filenames:
            if old_word in filename:
                old_file_path = os.path.join(current_path, filename)
                new_filename = filename.replace(old_word, new_word)
                new_file_path = os.path.join(current_path, new_filename)
                os.rename(old_file_path, new_file_path)
                print(f'Renamed file: {old_file_path} -> {new_file_path}')

        # Rename folders
        for dirname in dirnames:
            if old_word in dirname:
                old_dir_path = os.path.join(current_path, dirname)
                new_dirname = dirname.replace(old_word, new_word)
                new_dir_path = os.path.join(current_path, new_dirname)
                os.rename(old_dir_path, new_dir_path)
                print(f'Renamed directory: {old_dir_path} -> {new_dir_path}')


rename_recursively(directory_path, old_word, new_word)
