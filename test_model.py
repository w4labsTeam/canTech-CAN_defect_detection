
from pathlib import Path
import cv2
from ultralytics import YOLO


# ============================================================
# Configuration
# ============================================================

ROOT_DIR = Path(__file__).resolve().parent

MODEL_PATH = ROOT_DIR / "models" / "model_no2.pt"
TEST_DIR = ROOT_DIR / "test_images"
OUTPUT_DIR = ROOT_DIR / "testing_results"

# Start with a low threshold for diagnosis.
# This helps us see whether the model produces any detections.
CONFIDENCE_THRESHOLD = 0.001

# Set to None to let Ultralytics select the device automatically.
# Use "0" to explicitly select the first NVIDIA GPU.
DEVICE = None

# Press N or Space to view the next image.
# Press Q or Esc to quit.
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", "raw"}


def main():
    # --------------------------------------------------------
    # Validate paths
    # --------------------------------------------------------
    if not MODEL_PATH.is_file():
        print(f"[ERROR] Model not found: {MODEL_PATH}")
        return

    if not TEST_DIR.is_dir():
        print(f"[ERROR] Testing folder not found: {TEST_DIR}")
        return

    image_paths = sorted(
        path for path in TEST_DIR.iterdir()
        if path.is_file()
        and path.suffix.lower() in IMAGE_EXTENSIONS
    )

    if not image_paths:
        print(f"[ERROR] No images found in: {TEST_DIR}")
        return

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # --------------------------------------------------------
    # Load model once
    # --------------------------------------------------------
    print("Loading YOLO model...")

    model = YOLO(str(MODEL_PATH))

    print(f"Model: {MODEL_PATH}")
    print(f"Task: {model.task}")
    print(f"Classes: {model.names}")
    print(f"Confidence threshold: {CONFIDENCE_THRESHOLD}")
    print(f"Images found: {len(image_paths)}")
    print("\nStarting test...\n")

    if model.task != "obb":
        print(
            f"[WARNING] Expected an OBB model, "
            f"but model.task is '{model.task}'."
        )

    # --------------------------------------------------------
    # Test every image
    # --------------------------------------------------------
    total = 0
    detected = 0
    no_detection = 0

    for index, image_path in enumerate(image_paths, start=1):
        print("=" * 65)
        print(f"Image {index}/{len(image_paths)}: {image_path.name}")

        original = cv2.imread(str(image_path))

        if original is None:
            print("[ERROR] Could not read image.")
            continue

        # Run inference
        results = model.predict(
            source=original,
            conf=CONFIDENCE_THRESHOLD,
            device=DEVICE,
            verbose=False,
        )

        result = results[0]
        obb = result.obb

        # Print all detected oriented bounding boxes
        defect_found = False
        normal_found = False
        detections = []

        if obb is not None and len(obb) > 0:
            classes = obb.cls.cpu().tolist()
            confidences = obb.conf.cpu().tolist()

            for class_id, confidence in zip(classes, confidences):
                class_id = int(class_id)
                class_name = model.names.get(
                    class_id, f"class_{class_id}"
                )

                detections.append((class_name, confidence))

                print(
                    f"  Detection: {class_name:<10} "
                    f"Confidence: {confidence:.4f}"
                )

                if class_name.lower() == "defect":
                    defect_found = True
                elif class_name.lower() == "normal":
                    normal_found = True
                else:
                    print(
                        f"  [WARNING] Unexpected class ID: {class_id}"
                    )
        else:
            print("  No OBB detections.")

        # ----------------------------------------------------
        # Determine result
        # Defect takes priority if both classes are detected.
        # ----------------------------------------------------
        if defect_found:
            status = "DEFECTIVE"
            detected += 1
        elif normal_found:
            status = "NORMAL"
            detected += 1
        else:
            status = "NO DETECTION"
            no_detection += 1

        total += 1

        inference_ms = result.speed.get("inference", 0.0)

        print(f"  Final status: {status}")
        print(f"  Inference time: {inference_ms:.2f} ms")

        # ----------------------------------------------------
        # Create annotated image
        # ----------------------------------------------------
        annotated = result.plot()

        # Add status banner
        banner_color = (
            (0, 0, 255) if status == "DEFECTIVE"
            else (0, 180, 0) if status == "NORMAL"
            else (0, 165, 255)
        )

        cv2.rectangle(
            annotated, (0, 0), (annotated.shape[1], 55),
            banner_color, thickness=-1
        )

        cv2.putText(
            annotated,
            f"{status} | {inference_ms:.1f} ms",
            (15, 37),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.9,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )

        # ----------------------------------------------------
        # Display original and annotated image side by side
        # ----------------------------------------------------
        # Resize both for convenient viewing while preserving
        # their aspect ratios.
        max_height = 650

        def resize_for_display(image):
            scale = min(1.0, max_height / image.shape[0])
            width = int(image.shape[1] * scale)
            height = int(image.shape[0] * scale)

            return cv2.resize(
                image, (width, height),
                interpolation=cv2.INTER_AREA
            )

        original_display = resize_for_display(original)
        annotated_display = resize_for_display(annotated)

        # Make the images the same height if necessary
        display_height = max(
            original_display.shape[0],
            annotated_display.shape[0]
        )

        def pad_height(image, height):
            if image.shape[0] == height:
                return image

            return cv2.copyMakeBorder(
                image,
                0, height - image.shape[0],
                0, 0,
                cv2.BORDER_CONSTANT,
                value=(40, 40, 40),
            )

        original_display = pad_height(
            original_display, display_height
        )
        annotated_display = pad_height(
            annotated_display, display_height
        )

        # Add labels above each image
        label_height = 35

        original_panel = cv2.copyMakeBorder(
            original_display, label_height, 0, 0, 0,
            cv2.BORDER_CONSTANT, value=(40, 40, 40)
        )

        annotated_panel = cv2.copyMakeBorder(
            annotated_display, label_height, 0, 0, 0,
            cv2.BORDER_CONSTANT, value=(40, 40, 40)
        )

        cv2.putText(
            original_panel, "ORIGINAL",
            (10, 25), cv2.FONT_HERSHEY_SIMPLEX,
            0.7, (255, 255, 255), 2
        )

        cv2.putText(
            annotated_panel, "MODEL RESULT",
            (10, 25), cv2.FONT_HERSHEY_SIMPLEX,
            0.7, (255, 255, 255), 2
        )

        comparison = cv2.hconcat([
            original_panel,
            annotated_panel
        ])

        # Save annotated image
        output_path = OUTPUT_DIR / f"{image_path.stem}_result.jpg"
        cv2.imwrite(str(output_path), annotated)

        print(f"  Saved result: {output_path}")

        cv2.imshow("YOLO Model Test - Original vs Result", comparison)

        key = cv2.waitKey(0) & 0xFF

        if key in (ord("q"), 27):  # Q or Escape
            break

        # Any other key, including N or Space, advances.

    cv2.destroyAllWindows()

    # --------------------------------------------------------
    # Summary
    # --------------------------------------------------------
    print("\n" + "=" * 65)
    print("TEST SUMMARY")
    print("=" * 65)
    print(f"Images processed: {total}")
    print(f"Images with detections: {detected}")
    print(f"Images without detections: {no_detection}")
    print(f"Annotated images saved in: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
