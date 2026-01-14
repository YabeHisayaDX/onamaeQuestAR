import os
import shutil
import glob

INPUT_DIR = "new"    # ここに入れた写真を...
OUTPUT_DIR = "faces" # ここにリネームして移動する

print("---爆速リネーム---")

# 1. フォルダがなければ作る
if not os.path.exists(INPUT_DIR):
    os.makedirs(INPUT_DIR)
    print(f"📁 '{INPUT_DIR}' フォルダを作りました。ここに写真を放り込んでください！")
    exit()

if not os.path.exists(OUTPUT_DIR):
    os.makedirs(OUTPUT_DIR)

# 2. 写真があるかチェック
files = []
for ext in ["*.jpg", "*.jpeg", "*.png", "*.JPG", "*.PNG"]:
    files.extend(glob.glob(os.path.join(INPUT_DIR, ext)))

if len(files) == 0:
    print(f"'{INPUT_DIR}' フォルダの中身が空っぽです。")
    print(" 写真を入れてからもう一度実行してください。")
    exit()

print(f" {len(files)} 枚の写真が見つかりました。")

# 3. 名前の入力
target_name = input(">> 誰の写真ですか？ (例: Tanaka): ").strip()

if not target_name:
    print("名前が入力されませんでした。終了します。")
    exit()

# 4. すでに faces フォルダにある枚数を数える (続きから番号を振るため)
existing_files = glob.glob(os.path.join(OUTPUT_DIR, f"{target_name}_*"))
start_num = len(existing_files) + 1

print(f"🔄 '{target_name}_{start_num:02d}' から連番を振ります...")

# 5. リネーム & 移動実行
count = 0
for i, file_path in enumerate(files):
    # 拡張子 (.jpg とか) を取得
    ext = os.path.splitext(file_path)[1]
    
    # 新しい名前: Tanaka_01.jpg
    new_filename = f"{target_name}_{start_num + count:02d}{ext}"
    new_path = os.path.join(OUTPUT_DIR, new_filename)
    
    try:
        shutil.move(file_path, new_path)
        print(f"移動: {new_filename}")
        count += 1
    except Exception as e:
        print(f"❌ エラー: {file_path} -> {e}")

print("------------------------------------------------")

print(f"🎉 完了！ {count} 枚の写真を {OUTPUT_DIR} に収納しました。")
