import os
import pandas as pd
from server.service.predict import predict_image
from service.model_loader import load_models

model = load_models()

def load_image_list(file_path, name_column='image_path'):
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")
    
    try:
        df = pd.read_csv(file_path)
        if name_column not in df.columns:
            raise ValueError(f"CSV file must contain '{name_column}' column.")
        return df[name_column].tolist()
    except Exception as e:
        raise ValueError(f"Error reading CSV file: {e}")

def benchmark_model(image_list):
    results = []
    for image_path in image_list:
        with open(image_path, 'rb') as f:
            image_bytes = f.read()
        result = predict_image(image_bytes, model)
        results.append((image_path, 0 if result>0.5 else 1))
    return results

def add_label_to_image_list(image_list, label):
    labeled_list = []
    for image_path in image_list:
        labeled_list.append((image_path, label))