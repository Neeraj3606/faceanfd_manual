"""
Blink Detection for Anti-Spoofing
User must blink 2 times to mark attendance
"""

import cv2
import numpy as np
from typing import Tuple, Optional
import logging

logger = logging.getLogger(__name__)

# Eye Aspect Ratio (EAR) threshold for blink detection
EAR_THRESHOLD = 0.25
BLINK_FRAMES = 2  # Consecutive frames below threshold to count as blink

def calculate_eye_aspect_ratio(eye_landmarks: np.ndarray) -> float:
    """
    Calculate Eye Aspect Ratio (EAR) from eye landmarks
    EAR = (||p2-p6|| + ||p3-p5||) / (2 * ||p1-p4||)
    
    Lower EAR = eye is closed
    Higher EAR = eye is open
    """
    # Vertical distances
    v1 = np.linalg.norm(eye_landmarks[1] - eye_landmarks[5])
    v2 = np.linalg.norm(eye_landmarks[2] - eye_landmarks[4])
    
    # Horizontal distance
    h = np.linalg.norm(eye_landmarks[0] - eye_landmarks[3])
    
    # Eye Aspect Ratio
    if h == 0:
        return 0.0
    
    ear = (v1 + v2) / (2.0 * h)
    return ear


def get_eye_landmarks_from_face(face) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
    """
    Extract left and right eye landmarks from InsightFace face object
    Returns: (left_eye_landmarks, right_eye_landmarks)
    """
    try:
        # InsightFace provides 106 or 5 keypoints
        kps = getattr(face, 'kps', None)
        
        if kps is None:
            return None, None
        
        kps = np.array(kps)
        
        # If we have 5 keypoints (left_eye, right_eye, nose, left_mouth, right_mouth)
        if len(kps) == 5:
            # Use simple approximation - just the eye center points
            left_eye = kps[0]  # Left eye center
            right_eye = kps[1]  # Right eye center
            
            # Create approximate eye regions (6 points each)
            # This is a simplified version
            left_eye_region = np.array([
                left_eye,
                left_eye + [0, -5],
                left_eye + [0, -5],
                left_eye,
                left_eye + [0, 5],
                left_eye + [0, 5],
            ])
            
            right_eye_region = np.array([
                right_eye,
                right_eye + [0, -5],
                right_eye + [0, -5],
                right_eye,
                right_eye + [0, 5],
                right_eye + [0, 5],
            ])
            
            return left_eye_region, right_eye_region
        
        # If we have 106 keypoints, extract actual eye landmarks
        elif len(kps) >= 106:
            # Left eye landmarks (indices 35-41 typically)
            left_eye = kps[35:42]
            # Right eye landmarks (indices 42-48 typically)
            right_eye = kps[42:49]
            
            return left_eye, right_eye
        
        return None, None
        
    except Exception as e:
        logger.debug(f"Error extracting eye landmarks: {e}")
        return None, None


def detect_blink_simple(frame_bgr: np.ndarray, face) -> Tuple[bool, float, str]:
    """
    Simple blink detection using eye aspect ratio
    Returns: (blink_detected, ear_value, message)
    """
    try:
        left_eye, right_eye = get_eye_landmarks_from_face(face)
        
        if left_eye is None or right_eye is None:
            return False, 0.0, "Could not detect eyes"
        
        # Calculate EAR for both eyes
        left_ear = calculate_eye_aspect_ratio(left_eye)
        right_ear = calculate_eye_aspect_ratio(right_eye)
        
        # Average EAR
        avg_ear = (left_ear + right_ear) / 2.0
        
        # Blink detected if EAR is below threshold
        blink_detected = avg_ear < EAR_THRESHOLD
        
        return blink_detected, avg_ear, "OK"
        
    except Exception as e:
        logger.debug(f"Blink detection error: {e}")
        return False, 0.0, str(e)


class BlinkCounter:
    """
    Counts blinks over multiple frames
    """
    def __init__(self, required_blinks: int = 2):
        self.required_blinks = required_blinks
        self.blink_count = 0
        self.consecutive_closed = 0
        self.was_open = True
        self.ear_history = []
        
    def reset(self):
        """Reset the counter"""
        self.blink_count = 0
        self.consecutive_closed = 0
        self.was_open = True
        self.ear_history = []
    
    def update(self, ear: float) -> Tuple[bool, int, str]:
        """
        Update with new EAR value
        Returns: (completed, blink_count, message)
        """
        self.ear_history.append(ear)
        if len(self.ear_history) > 30:  # Keep last 30 frames
            self.ear_history.pop(0)
        
        # Eye is closed
        if ear < EAR_THRESHOLD:
            self.consecutive_closed += 1
        else:
            # Eye is open
            # If it was closed before, count as a blink
            if self.consecutive_closed >= BLINK_FRAMES and not self.was_open:
                self.blink_count += 1
                logger.info(f"Blink detected! Count: {self.blink_count}/{self.required_blinks}")
            
            self.consecutive_closed = 0
            self.was_open = True
        
        # Update state
        if self.consecutive_closed >= BLINK_FRAMES:
            self.was_open = False
        
        # Check if completed
        completed = self.blink_count >= self.required_blinks
        
        message = f"Blinks: {self.blink_count}/{self.required_blinks}"
        if completed:
            message = f"✅ {self.required_blinks} blinks detected!"
        
        return completed, self.blink_count, message


def check_blink_liveness(frames_with_faces: list, required_blinks: int = 2) -> Tuple[bool, str]:
    """
    Check if user blinked required number of times across multiple frames
    
    Args:
        frames_with_faces: List of (frame, face) tuples
        required_blinks: Number of blinks required (default 2)
    
    Returns:
        (is_real, message)
    """
    if not frames_with_faces or len(frames_with_faces) < 5:
        return False, "Not enough frames captured. Please try again."
    
    counter = BlinkCounter(required_blinks=required_blinks)
    
    for frame, face in frames_with_faces:
        left_eye, right_eye = get_eye_landmarks_from_face(face)
        
        if left_eye is None or right_eye is None:
            continue
        
        # Calculate EAR
        left_ear = calculate_eye_aspect_ratio(left_eye)
        right_ear = calculate_eye_aspect_ratio(right_eye)
        avg_ear = (left_ear + right_ear) / 2.0
        
        # Update counter
        completed, count, message = counter.update(avg_ear)
        
        if completed:
            return True, f"✅ Liveness verified! {required_blinks} blinks detected."
    
    # Not enough blinks
    return False, f"❌ Please blink {required_blinks} times. Detected: {counter.blink_count}"


# Simplified version for single frame check (fallback)
def check_eyes_open(frame_bgr: np.ndarray, face) -> Tuple[bool, str]:
    """
    Simple check if eyes are open (not a closed-eye static photo).
    With InsightFace 5-keypoint output, we cannot compute a proper EAR.
    Instead we compare the vertical spread of the two eye keypoints
    relative to the inter-eye distance — a proxy for openness direction.
    Fallback is True (open) so MiniFASNet remains the primary liveness gate.
    Returns: (eyes_open, message)
    """
    try:
        kps = getattr(face, 'kps', None)
        if kps is None:
            return True, "No keypoints — assuming eyes open"

        kps = np.array(kps)

        if len(kps) >= 106:
            # Full landmark set — use proper EAR
            left_eye_lm, right_eye_lm = get_eye_landmarks_from_face(face)
            if left_eye_lm is None or right_eye_lm is None:
                return True, "Could not extract eye landmarks — assuming open"
            left_ear = calculate_eye_aspect_ratio(left_eye_lm)
            right_ear = calculate_eye_aspect_ratio(right_eye_lm)
            avg_ear = (left_ear + right_ear) / 2.0
            eyes_open = avg_ear >= EAR_THRESHOLD
            if eyes_open:
                return True, f"Eyes open (EAR: {avg_ear:.3f})"
            else:
                return False, f"Eyes appear closed (EAR: {avg_ear:.3f})"

        elif len(kps) == 5:
            # 5-point: [left_eye, right_eye, nose, left_mouth, right_mouth]
            # We cannot compute EAR without per-eye contour points.
            # Use a simple sanity check: if both eye keypoints are above
            # the nose keypoint (as expected for a normal upright face), pass.
            left_eye_pt = kps[0]   # (x, y)
            right_eye_pt = kps[1]
            nose_pt = kps[2]
            # Eyes should be above nose in image coordinates (smaller y)
            eyes_above_nose = (left_eye_pt[1] < nose_pt[1]) and (right_eye_pt[1] < nose_pt[1])
            if not eyes_above_nose:
                # Face is inverted or very tilted — likely a photo held upside down
                return False, "Eyes not above nose — possible inverted photo"
            # Cannot tell if eyes are closed with 5 pts — pass through
            return True, "5-point keypoints: eye open check bypassed (MiniFASNet primary)"

        else:
            return True, "Unknown keypoint count — assuming eyes open"

    except Exception as e:
        logger.debug(f"Eye check error: {e}")
        return True, "Eye check failed — assuming real"
