import cv2
import requests

API_URL = "http://127.0.0.1:8000/attendance/mark"


def main():
    cap = cv2.VideoCapture(0)

    if not cap.isOpened():
        print("❌ Camera open nahi ho raha (permission/device issue)")
        return

    print("✅ Camera ON")
    print("👉 Press 's' = Snap + Mark Attendance")
    print("👉 Press 'q' = Quit")

    while True:
        ret, frame = cap.read()
        if not ret:
            print("❌ Frame read nahi hua")
            break

        cv2.imshow("Face Attendance - Press s to Mark", frame)

        key = cv2.waitKey(1) & 0xFF

        if key == ord("s"):
            ok, buffer = cv2.imencode(".jpg", frame)
            if not ok:
                print("❌ Image encode failed")
                continue

            files = {"file": ("snap.jpg", buffer.tobytes(), "image/jpeg")}

            try:
                res = requests.post(API_URL, files=files, timeout=30)
                data = res.json()

                # ✅ Print clean message
                if data.get("ok") and data.get("marked") is True:
                    print("✅ MARKED:", data.get("name"), "|", data.get("student_id"))
                elif data.get("ok") and data.get("marked") is False:
                    print("ℹ️ ALREADY MARKED:", data.get("name"), "|", data.get("student_id"))
                else:
                    print("❌", data.get("message"))

            except Exception as e:
                print("❌ API Error:", e)

        elif key == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()