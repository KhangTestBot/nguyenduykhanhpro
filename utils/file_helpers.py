import os

def read_prompts_from_file(filepath: str) -> list:
    """Reads a text file and returns a list of non-empty prompts."""
    prompts = []
    if not os.path.exists(filepath):
        return prompts
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    prompts.append(line)
    except Exception as e:
        print(f"Error reading prompt file {filepath}: {e}")
        
    return prompts

def get_image_files(directory: str) -> list:
    """Returns a list of image files (paths) from the given directory."""
    images = []
    if not os.path.exists(directory):
        return images
        
    valid_extensions = ('.png', '.jpg', '.jpeg', '.webp')
    try:
        for filename in os.listdir(directory):
            if filename.lower().endswith(valid_extensions):
                images.append(os.path.join(directory, filename))
    except Exception as e:
        print(f"Error reading image directory {directory}: {e}")
        
    return images
