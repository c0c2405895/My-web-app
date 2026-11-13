import json
import os
import random
import secrets
import uuid
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

from flask import Flask, jsonify, redirect, render_template, request, send_from_directory, session, url_for
from werkzeug.utils import secure_filename


BASE_DIR = Path(__file__).resolve().parent
DATA_FILE = BASE_DIR / "app" / "wardrobe.json"
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)
DATA_FILE.parent.mkdir(exist_ok=True)

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.environ.get("COOKIE_SECURE") == "1"
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}


@app.after_request
def disable_browser_cache(response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


DEFAULT_DATA = {
    "items": [
        {"id": "demo-1", "name": "ライトブルーシャツ", "category": "トップス", "color": "ブルー", "image": None},
        {"id": "demo-2", "name": "ワイドデニム", "category": "ボトムス", "color": "ネイビー", "image": None},
        {"id": "demo-3", "name": "ベージュトレンチ", "category": "アウター", "color": "ベージュ", "image": None},
        {"id": "demo-4", "name": "白スニーカー", "category": "シューズ", "color": "ホワイト", "image": None},
    ],
    "feedback": [],
    "settings": {"notifications": True, "notification_time": "07:30", "location": "東京"},
    "profile": {"full_name": "", "display_name": "Alex", "email": "", "phone": "", "avatar": None},
}


def load_data():
    if not DATA_FILE.exists():
        save_data(DEFAULT_DATA)
    try:
        data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        data.setdefault("profile", json.loads(json.dumps(DEFAULT_DATA["profile"])))
        for key, value in DEFAULT_DATA["profile"].items():
            data["profile"].setdefault(key, value)
        known_images = {item.get("image") for item in data.get("items", [])}
        imported = False
        for photo in UPLOAD_DIR.iterdir():
            if not photo.is_file() or photo.name.startswith("avatar_") or not allowed_file(photo.name):
                continue
            image_url = f"/uploads/{photo.name}"
            if image_url in known_images:
                continue
            stem = photo.stem.replace("_", " ").replace("-", " ").strip()
            attributes = infer_item_attributes(stem)
            data["items"].insert(0, {
                "id": f"uploaded-{uuid.uuid4().hex}",
                "name": stem or "アップロードした服",
                **attributes,
                "image": image_url,
            })
            known_images.add(image_url)
            imported = True
        if data.get("warmth_scale") != 100:
            for item in data.get("items", []):
                item.update(infer_item_attributes(item.get("name"), item.get("category"), item.get("color")))
            data["warmth_scale"] = 100
            imported = True
        for item in data.get("items", []):
            inferred = infer_item_attributes(item.get("name"), item.get("category"), item.get("color"))
            if (
                inferred["category"] != item.get("category")
                or "material" not in item
                or "warmth" not in item
                or "warmth_label" not in item
            ):
                item.update(inferred)
                imported = True
        if imported:
            save_data(data)
        return data
    except (OSError, json.JSONDecodeError):
        return json.loads(json.dumps(DEFAULT_DATA))


def save_data(data):
    DATA_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def is_available_item(item):
    image = item.get("image")
    if not image or not image.startswith("/uploads/"):
        return False
    filename = Path(image.removeprefix("/uploads/")).name
    return bool(filename) and (UPLOAD_DIR / filename).is_file()


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def infer_item_attributes(name, category=None, color=None):
    """Infer useful outfit attributes locally from a Japanese item name."""
    text = (name or "").lower()
    category = category or "トップス"
    color = color or "その他"
    category_words = {
        "アウター": ("アウター", "コート", "ジャケット", "ブルゾン", "ダウン", "トレンチ", "カーディガン", "パーカー", "parka", "mountain parka", "shell"),
        "ボトムス": ("パンツ", "デニム", "ジーンズ", "スカート", "チノ", "スラックス"),
        "シューズ": ("スニーカー", "ブーツ", "サンダル", "シューズ", "靴"),
        "ワンピース": ("ワンピース", "ドレス"),
    }
    for candidate, words in category_words.items():
        if any(word in text for word in words):
            category = candidate
            break
    material = "混紡"
    warmth = 50
    warmth_label = "普通"
    material_scores = (
        (("ダウン", "シュラフ", "寝袋"), "ダウン", 95, "非常に暖かい"),
        (("マウンテンパーカー", "ハードシェル"), "防水シェル", 75, "防寒向き"),
        (("ウール", "カシミヤ"), "ウール", 78, "厚手・暖かい"),
        (("フリース", "ボア", "裏起毛"), "フリース", 68, "厚手・暖かい"),
        (("ニット",), "ニット", 58, "やや厚手"),
        (("リネン", "麻"), "リネン", 18, "薄手・涼しい"),
        (("コットン", "綿", "シャツ", "tシャツ"), "コットン", 38, "普通"),
        (("ポリエステル",), "ポリエステル", 45, "普通"),
    )
    for words, detected_material, detected_warmth, detected_label in material_scores:
        if any(word in text for word in words):
            material, warmth, warmth_label = detected_material, detected_warmth, detected_label
            break
    if warmth == 50 and any(word in text for word in ("厚手", "コート")):
        warmth, warmth_label = 72, "厚手・暖かい"
    elif any(word in text for word in ("ジャケット", "ブルゾン", "カーディガン", "パーカー", "トレンチ", "スウェット")):
        warmth, warmth_label = 58, "やや厚手"
    elif any(word in text for word in ("半袖", "ノースリーブ", "タンクトップ", "薄手", "シャツ", "Tシャツ", "ブラウス", "サンダル")):
        warmth, warmth_label = 18, "薄手・涼しい"
    return {
        "category": category,
        "color": color,
        "material": material,
        "warmth": warmth,
        "warmth_label": warmth_label,
    }


def classify_item(filename, category, color):
    """Local fallback classifier; replace with a vision API without changing the UI contract."""
    name = Path(filename).stem.replace("_", " ").replace("-", " ").strip() or "新しいアイテム"
    attributes = infer_item_attributes(name, category, color)
    return name.title(), attributes


def weather_for(location):
    # Geocoding + forecast are intentionally best-effort so the demo works offline.
    fallback = {
        "location": location or "東京",
        "temperature": 18,
        "feels_like": 17,
        "rain": False,
        "condition": "晴れ",
        "temperature_min": None,
        "temperature_max": None,
    }
    try:
        geo_url = "https://geocoding-api.open-meteo.com/v1/search?" + urlencode(
            {"name": location or "東京", "count": 1, "language": "ja", "format": "json"}
        )
        with urlopen(geo_url, timeout=3) as response:
            geo = json.loads(response.read().decode("utf-8"))
        result = (geo.get("results") or [None])[0]
        if not result and (location or "").strip() in {"東京", "Tokyo", "東京23区"}:
            result = {"name": "東京", "latitude": 35.6762, "longitude": 139.6503}
        if not result:
            return fallback
        forecast_url = "https://api.open-meteo.com/v1/forecast?" + urlencode({
                "latitude": result["latitude"],
                "longitude": result["longitude"],
                "current": "temperature_2m,apparent_temperature,precipitation,weather_code",
                "daily": "temperature_2m_max,temperature_2m_min,weather_code",
                "forecast_days": 1,
                "timezone": "auto",
            })
        with urlopen(forecast_url, timeout=10) as response:
            forecast_data = json.loads(response.read().decode("utf-8"))
        forecast = forecast_data.get("current", {})
        daily = forecast_data.get("daily", {})
        daily_max = (daily.get("temperature_2m_max") or [None])[0]
        daily_min = (daily.get("temperature_2m_min") or [None])[0]
        temperature = forecast.get("temperature_2m", daily_max if daily_max is not None else 18)
        code = ((daily.get("weather_code") or [forecast.get("weather_code", 0)])[0] or 0)
        condition = "雨" if code >= 51 else "くもり" if code >= 1 else "晴れ"
        return {
            "location": result.get("name", location),
            "temperature": round(temperature),
            "feels_like": round(forecast.get("apparent_temperature", 17)),
            "rain": code >= 51 or forecast.get("precipitation", 0) > 0,
            "condition": condition,
            "temperature_min": round(daily_min) if daily_min is not None else None,
            "temperature_max": round(daily_max) if daily_max is not None else None,
        }
    except (OSError, ValueError, KeyError, TypeError):
        return fallback


def make_outfit(data, weather):
    items = [item for item in data["items"] if is_available_item(item)]
    feedback = data.get("feedback", [])
    latest_feedback = {}
    for entry in feedback:
        latest_feedback[entry["item_id"]] = entry["value"]
    disliked = {item_id for item_id, value in latest_feedback.items() if value == "dislike"}
    liked_colors = [item["color"] for item in items
                    if latest_feedback.get(item["id"]) == "like"]
    preferred_items = [item for item in items if item["id"] not in disliked]

    target_warmth = (
        95 if weather["temperature"] < 5 else
        75 if weather["temperature"] < 10 else
        58 if weather["temperature"] < 16 else
        45 if weather["temperature"] < 23 else 25
    )

    used_ids = set()

    def pick(category, minimum_warmth=0):
        candidates = [item for item in preferred_items
                      if item["category"] == category
                      and item["id"] not in used_ids
                      and item.get("warmth", 50) >= minimum_warmth]
        if not candidates:
            candidates = [item for item in items
                          if item["category"] == category
                          and item["id"] not in used_ids
                          and item.get("warmth", 50) >= minimum_warmth]
        if liked_colors:
            preferred = [item for item in candidates if item["color"] in liked_colors]
            candidates = preferred or candidates
        if not candidates:
            return None
        closest = min(abs(item.get("warmth", 50) - target_warmth) for item in candidates)
        candidates = [item for item in candidates if abs(item.get("warmth", 50) - target_warmth) == closest]
        item = random.choice(candidates)
        used_ids.add(item["id"])
        return item

    top_minimum_warmth = 45 if weather["temperature"] <= 10 else 35 if weather["temperature"] < 16 else 0
    selected_by_category = {
        "トップス": pick("トップス", top_minimum_warmth),
        "ボトムス": pick("ボトムス"),
    }
    if weather["temperature"] < 15:
        selected_by_category["アウター"] = pick("アウター")
    if weather["rain"]:
        selected_by_category["シューズ"] = pick("シューズ")
    missing = []
    for category, item in selected_by_category.items():
        if item is None and category in {"トップス", "ボトムス", "アウター"}:
            missing.append(category)
    selected = [item for item in selected_by_category.values() if item]
    selected = [item for item in selected if item]
    temp = weather["temperature"]
    temperature_reason = (
        "厚手の防寒アイテムが必要な気温です。"
        if temp < 10 else
        "長袖や軽いアウターがちょうどよい気温です。"
        if temp < 16 else
        "長袖や薄手の羽織りを取り入れやすい気温です。"
        if temp < 23 else
        "薄手で軽やかな服が過ごしやすい気温です。"
        if temp < 28 else
        "涼しく通気性のよい服がおすすめの気温です。"
    )
    reasons = [f"現在{temp}°C。{temperature_reason}"]
    if weather["rain"]:
        reasons.append("雨予報のため、足元を汚れにくいアイテムにしています。")
    if liked_colors:
        reasons.append(f"これまで好きと評価した色（{', '.join(sorted(set(liked_colors)))}）を取り入れています。")
    if not selected:
        reasons = ["まずはワードローブに服を登録すると、あなた専用の提案が始まります。"]
    return {
        "items": selected,
        "reasons": reasons,
        "missing": sorted(set(missing)),
        "purchase_suggestions": [],
    }


@app.route("/")
def index():
    if not session.get("logged_in"):
        return redirect(url_for("login"))
    return render_template("index.html", profile=load_data()["profile"])


@app.route("/wardrobe")
def wardrobe():
    if not session.get("logged_in"):
        return redirect(url_for("login"))
    return render_template("wardrobe.html", profile=load_data()["profile"])


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        identifier = request.form.get("identifier", "").strip()
        password = request.form.get("password", "")
        if not identifier or not password:
            error = "メールアドレスまたは電話番号とパスワードを入力してください。"
        else:
            data = load_data()
            if identifier.isdigit():
                data["profile"]["phone"] = identifier
            else:
                data["profile"]["email"] = identifier
            save_data(data)
            session["logged_in"] = True
            return redirect(url_for("index"))
    return render_template("login.html", error=error)


@app.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/settings", methods=["GET", "POST"])
def user_settings():
    if not session.get("logged_in"):
        return redirect(url_for("login"))
    data = load_data()
    error = None
    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        display_name = request.form.get("display_name", "").strip()
        email = request.form.get("email", "").strip()
        phone = request.form.get("phone", "").strip()
        if not display_name:
            error = "表示名を入力してください。"
        elif len(full_name) > 80 or len(display_name) > 40 or len(email) > 254 or len(phone) > 30:
            error = "入力内容が長すぎます。"
        else:
            data["profile"].update({
                "full_name": full_name,
                "display_name": display_name,
                "email": email,
                "phone": phone,
            })
            avatar = request.files.get("avatar")
            if avatar and avatar.filename:
                if not allowed_file(avatar.filename):
                    error = "アバターはPNG、JPG、JPEG、WEBPの画像を選択してください。"
                else:
                    stored = f"avatar_{uuid.uuid4().hex}_{secure_filename(avatar.filename)}"
                    avatar.save(UPLOAD_DIR / stored)
                    data["profile"]["avatar"] = f"/uploads/{stored}"
            if not error:
                save_data(data)
                return render_template("user-settings.html", profile=data["profile"], saved=True)
    return render_template("user-settings.html", profile=data["profile"], error=error, saved=False)


@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(UPLOAD_DIR, filename)


@app.get("/api/dashboard")
def dashboard():
    if not session.get("logged_in"):
        return jsonify({"error": "ログインが必要です。"}), 401
    data = load_data()
    weather = weather_for(data["settings"].get("location", "東京"))
    available_items = [item for item in data["items"] if is_available_item(item)]
    return jsonify({"items": available_items, "feedback": data["feedback"], "settings": data["settings"],
                    "weather": weather, "outfit": make_outfit(data, weather)})


@app.post("/api/items")
def add_item():
    if not session.get("logged_in"):
        return jsonify({"error": "ログインが必要です。"}), 401
    data = load_data()
    photo = request.files.get("photo")
    if not photo or not photo.filename or not allowed_file(photo.filename):
        return jsonify({"error": "PNG、JPG、JPEG、WEBPの画像を選択してください。"}), 400
    item_name = request.form.get("name", "").strip()
    if not item_name:
        item_name = Path(photo.filename).stem.replace("_", " ").replace("-", " ").strip()
    if not item_name:
        item_name = "新しいアイテム"
    if len(item_name) > 80:
        return jsonify({"error": "服の名前は80文字以内で入力してください。"}), 400
    original = secure_filename(photo.filename)
    stored = f"{uuid.uuid4().hex}_{original}"
    photo.save(UPLOAD_DIR / stored)
    attributes = infer_item_attributes(item_name)
    item = {"id": uuid.uuid4().hex, "name": item_name, **attributes,
            "analysis_source": "アプリ内ルール判定",
            "image": f"/uploads/{stored}"}
    data["items"].insert(0, item)
    save_data(data)
    return jsonify(item), 201


@app.post("/api/feedback")
def feedback():
    if not session.get("logged_in"):
        return jsonify({"error": "ログインが必要です。"}), 401
    payload = request.get_json(silent=True) or {}
    if payload.get("item_id") not in {item["id"] for item in load_data()["items"]}:
        return jsonify({"error": "対象のアイテムが見つかりません。"}), 404
    if payload.get("value") not in {"like", "dislike"}:
        return jsonify({"error": "評価はlikeまたはdislikeを指定してください。"}), 400
    data = load_data()
    data["feedback"].append({"item_id": payload["item_id"], "value": payload["value"],
                             "created_at": datetime.now().isoformat(timespec="seconds")})
    save_data(data)
    return jsonify({"ok": True})


@app.put("/api/settings")
def settings():
    if not session.get("logged_in"):
        return jsonify({"error": "ログインが必要です。"}), 401
    data = load_data()
    payload = request.get_json(silent=True) or {}
    data["settings"].update({key: payload[key] for key in ("notifications", "notification_time", "location") if key in payload})
    save_data(data)
    return jsonify(data["settings"])


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "5000")),
        debug=os.environ.get("FLASK_DEBUG") == "1",
    )
