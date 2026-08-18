import cv2
import numpy as np
import os
from PIL import Image, ImageOps

class KinderSortAIEngine:
    """
    KinderSort Lite - Enhanced AI Engine for Low-Resource Environments
    Author: Member 1
    Features:
    - Automatic Image Resizing (reduces RAM & CPU load)
    - Lightweight CPU-Only Face Detection / Feature Extraction
    - Fully Offline Capable
    """
    
    def __init__(self, target_size=(640, 480)):
        self.target_size = target_size
        print("[INFO] KinderSort Lite AI Engine Initialized (CPU Mode).")

    def preprocess_image(self, image_path):
        """
        Low-Resource Optimization Strategy 1: Image Resizing & Normalization
        Scales down high-res photos to prevent high memory usage on low-end laptops.
        """
        try:
            img = Image.open(image_path)
            img = ImageOps.exif_transpose(img)
            img.thumbnail(self.target_size, Image.Resampling.LANCZOS)
            cv_img = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
            return cv_img
        except Exception as e:
            print(f"[ERROR] Failed to preprocess image {image_path}: {e}")
            return None

    def detect_and_extract_faces(self, image_path):
        """
        Core AI Task: Enhanced Face Detection optimized for CPU-only execution.
        """
        cv_img = self.preprocess_image(image_path)
        if cv_img is None:
            return []

        gray = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)
        face_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
        )
        
        faces = face_cascade.detectMultiScale(
            gray, 
            scaleFactor=1.1, 
            minNeighbors=5, 
            minSize=(30, 30)
        )
        
        results = []
        for (x, y, w, h) in faces:
            face_roi = cv_img[y:y+h, x:x+w]
            results.append({
                "bbox": (x, y, w, h),
                "face_img": face_roi
            })
            
        return results

if __name__ == "__main__":
    engine = KinderSortAIEngine()
    print("AI Engine test complete. Ready for integration.")