"""The safety talks in the five languages most spoken at home in the United States after English.

Only the worker facing talk is translated; the app, the citations and the letters stay in
English (see "Languages" in README.md). Every translation here, the Spanish one in writer.py
included, was drafted with an AI assistant and must be checked by a native speaker before a plant
uses it on the floor.

No text here writes a digit: counts arrive through {{topic_reports}} and {{since}}, so the
Decision critic can still treat any digit outside a placeholder as untraced.
"""

from __future__ import annotations

from typing import Any


# Code to name, in the order of speakers age 5 and over (ACS 2025, table B16001).
LANGUAGES = {"es": "Spanish", "zh": "Chinese", "tl": "Tagalog", "vi": "Vietnamese", "ar": "Arabic"}
RIGHT_TO_LEFT = {"ar"}

LEADS = {
    "en": "Plants like yours reported {{topic_reports}} severe injuries of this kind since {{since}}.",
    "es": "En las plantas como la suya hubo {{topic_reports}} lesiones graves de este tipo desde {{since}}.",
    "zh": "与您同类的工厂自{{since}}年以来报告了{{topic_reports}}起此类严重伤害。",
    "tl": "Ang mga planta na tulad ng sa inyo ay nag-ulat ng {{topic_reports}} malubhang pinsala ng ganitong uri "
    "mula noong {{since}}.",
    "vi": "Các nhà máy như của bạn đã báo cáo {{topic_reports}} ca chấn thương nghiêm trọng loại này kể từ năm {{since}}.",
    "ar": "أبلغت مصانع مثل مصنعكم عن {{topic_reports}} إصابة خطيرة من هذا النوع منذ عام {{since}}.",
}

TRANSLATIONS: dict[str, dict[str, dict[str, Any]]] = {
    "lockout": {
        "zh": {
            "title": "伸手之前先上锁",
            "why": "机器会毫无预警地启动。排除卡料、清洁或快速调整时，手最容易伸进原本有防护罩的地方。",
            "points": [
                "停机并切断所有能源：电、气、液压、重力和储能弹簧。",
                "在每个隔离点挂上您自己的锁和标签。您的锁，您的钥匙。",
                "伸手之前先尝试启动机器，确认无法启动后再把开关恢复到关闭位置。",
                "如果卡料反复出现，请告诉主管。不要在机器运行时排除卡料。",
            ],
            "close": "问自己：还有什么能量能让这台机器动起来？如果不确定，就说明还没有上锁。",
        },
        "tl": {
            "title": "Mag-lockout bago ipasok ang kamay",
            "why": "Umaandar ang makina nang walang babala. Sa pag-alis ng bara, paglilinis o mabilis na pag-aayos "
            "pumapasok ang kamay sa dating kinalalagyan ng guard.",
            "points": [
                (
                    "Patayin ang makina at putulin ang lahat ng pinagmumulan ng enerhiya: kuryente, hangin, hydraulic, "
                    "gravity at nakaimbak na spring."
                ),
                "Ilagay ang sarili mong kandado at tag sa bawat isolation point. Iyong kandado, iyong susi.",
                "Subukang paandarin ang makina bago ipasok ang kamay, saka ibalik sa off ang kontrol.",
                "Kung paulit-ulit ang bara, sabihin sa iyong supervisor. Huwag itong alisin habang umaandar ang makina.",
            ],
            "close": "Itanong: anong enerhiya pa ang puwedeng magpagalaw sa makinang ito? Kung hindi ka sigurado, "
            "hindi pa ito naka-lockout.",
        },
        "vi": {
            "title": "Khóa nguồn trước khi đưa tay vào",
            "why": "Máy có thể chạy mà không báo trước. Lúc gỡ kẹt, vệ sinh hay chỉnh nhanh là lúc tay đưa vào chỗ "
            "lẽ ra có tấm che.",
            "points": [
                "Dừng máy và ngắt mọi nguồn năng lượng: điện, khí nén, thủy lực, trọng lực và lò xo tích năng.",
                "Gắn ổ khóa và thẻ của chính bạn vào từng điểm cách ly. Khóa của bạn, chìa của bạn.",
                "Thử khởi động máy trước khi đưa tay vào, rồi đưa công tắc về vị trí tắt.",
                "Nếu máy kẹt lặp lại, hãy báo người giám sát. Không gỡ kẹt khi máy đang chạy.",
            ],
            "close": "Hãy tự hỏi: còn năng lượng nào có thể làm máy chuyển động? Nếu chưa chắc, tức là máy chưa được khóa.",
        },
        "ar": {
            "title": "اقفل الطاقة قبل أن تمد يدك",
            "why": "تبدأ الآلات بالعمل دون إنذار. أثناء إزالة انحشار أو التنظيف أو ضبط سريع تمتد الأيدي إلى حيث كان الواقي.",
            "points": [
                "أوقف الآلة وافصل كل مصادر الطاقة: الكهرباء والهواء المضغوط والهيدروليك والجاذبية والنوابض المشحونة.",
                "ضع قفلك وبطاقتك الخاصين على كل نقطة عزل. قفلك أنت، ومفتاحك أنت.",
                "حاول تشغيل الآلة قبل أن تمد يدك، ثم أعد مفتاح التحكم إلى وضع الإيقاف.",
                "إذا تكرر الانحشار فأبلغ مشرفك. لا تُزِله والآلة تعمل.",
            ],
            "close": "اسأل نفسك: ما الطاقة التي ما زالت قادرة على تحريك هذه الآلة؟ إن لم تكن متأكدًا فهي غير مقفلة.",
        },
    },
    "machine guarding": {
        "zh": {
            "title": "防护罩必须装好",
            "why": "滚筒、刀片和皮带卷入手套或袖子的速度比任何人反应都快。",
            "points": [
                "绝不要在防护罩被拆除、弯曲或被绕过时操作机器。",
                "手要远离作业点；使用推杆和送料工具。",
                "在开班前报告缺失或损坏的防护罩。",
            ],
            "close": "如果防护罩让工作变慢，请说出来。拆掉它不是解决办法。",
        },
        "tl": {
            "title": "Laging nakakabit ang guard",
            "why": "Ang roller, talim at belt ay humihila ng guwantes o manggas nang mas mabilis kaysa makakakilos ang "
            "sinuman.",
            "points": [
                "Huwag kailanman paandarin ang makina kung tinanggal, baluktot o nilampasan ang guard.",
                "Ilayo ang kamay sa point of operation; gumamit ng push stick at kasangkapang pang-feed.",
                "I-report ang nawawala o sirang guard bago magsimula ang shift.",
            ],
            "close": "Kung pinababagal ng guard ang trabaho, sabihin ito. Hindi solusyon ang pagtanggal dito.",
        },
        "vi": {
            "title": "Luôn giữ tấm che máy",
            "why": "Trục cán, lưỡi dao và dây đai cuốn găng tay hay tay áo vào nhanh hơn bất kỳ ai kịp phản ứng.",
            "points": [
                "Không bao giờ chạy máy khi tấm che đã bị tháo, cong vênh hay bị vô hiệu hóa.",
                "Giữ tay tránh xa vùng gia công; dùng que đẩy và dụng cụ cấp phôi.",
                "Báo ngay tấm che bị thiếu hoặc hỏng trước khi bắt đầu ca.",
            ],
            "close": "Nếu tấm che làm chậm công việc, hãy nói ra. Tháo nó ra không phải là cách sửa.",
        },
        "ar": {
            "title": "الواقيات تبقى في مكانها",
            "why": "تسحب البكرات والشفرات والسيور القفاز أو الكم أسرع مما يستطيع أي شخص أن يتفاعل.",
            "points": [
                "لا تشغّل أبدًا آلة واقيها منزوع أو مثني أو معطّل.",
                "أبعد يديك عن نقطة التشغيل؛ استخدم عصي الدفع وأدوات التغذية.",
                "أبلغ عن أي واقٍ مفقود أو تالف قبل بدء الوردية.",
            ],
            "close": "إذا كان الواقي يبطئ العمل فقل ذلك. نزعه ليس هو الحل.",
        },
    },
    "fall": {
        "zh": {
            "title": "每一个边缘都可能坠落",
            "why": "大多数坠落发生在短暂的例行工作中：一步踏上拖车，或在夹层边缘探头看一眼。",
            "points": [
                "使用护栏、安全带或升降设备；绝不要越过没有防护的边缘。",
                "盖好并标出孔洞和天窗。",
                "上下设备时保持三点接触。",
            ],
            "close": "上去之前先问：如果滑倒了，什么在保护您？",
        },
        "tl": {
            "title": "Bawat gilid ay puwedeng pagkahulugan",
            "why": "Karamihan ng pagkahulog ay nangyayari sa maiikli at karaniwang gawain: isang hakbang paakyat sa "
            "trailer, mabilis na silip sa gilid ng mezzanine.",
            "points": [
                "Gamitin ang guardrail, harness o lift; huwag lumampas sa gilid na walang proteksyon.",
                "Takpan at markahan ang mga butas at skylight.",
                "Panatilihin ang tatlong punto ng kapit kapag umaakyat at bumababa sa kagamitan.",
            ],
            "close": "Bago umakyat, itanong kung paano ka protektado kapag nadulas ka.",
        },
        "vi": {
            "title": "Mép nào cũng có thể ngã",
            "why": "Phần lớn các vụ ngã xảy ra trong việc ngắn, quen tay: bước lên rơ-moóc, ngó qua mép sàn lửng.",
            "points": [
                "Dùng lan can, dây an toàn hoặc xe nâng người; không bao giờ bước qua mép không có che chắn.",
                "Che và đánh dấu các lỗ hổng và giếng trời.",
                "Giữ ba điểm tiếp xúc khi leo lên, leo xuống thiết bị.",
            ],
            "close": "Trước khi lên cao, hãy hỏi: nếu trượt chân, điều gì bảo vệ bạn?",
        },
        "ar": {
            "title": "كل حافة قد تعني سقوطًا",
            "why": "تحدث معظم حالات السقوط في أعمال قصيرة ومعتادة: خطوة إلى مقطورة، أو نظرة سريعة من حافة طابق علوي.",
            "points": [
                "استخدم الدرابزين أو الحزام أو الرافعة؛ لا تتجاوز أبدًا حافة غير محمية.",
                "غطِّ الفتحات والمناور وضع عليها علامات.",
                "حافظ على ثلاث نقاط تلامس عند الصعود إلى المعدات والنزول منها.",
            ],
            "close": "قبل أن تصعد، اسأل: كيف أنت محمي إذا انزلقت؟",
        },
    },
    "forklift": {
        "zh": {
            "title": "叉车与行人",
            "why": "叉车司机常常看不见走在货物后面的人。",
            "points": [
                "只有经过培训和考核的人员才能驾驶叉车。",
                "在标示的通道内行走，穿越前先与司机目光接触。",
                "货物要放低放稳；绝不要站在货叉上。",
            ],
            "close": "如果您看不到司机的眼睛，司机也看不到您。",
        },
        "tl": {
            "title": "Forklift at mga tao",
            "why": "Madalas hindi nakikita ng forklift operator ang taong naglalakad sa likod ng karga.",
            "points": [
                "Ang mga sinanay at nasuring operator lang ang nagmamaneho ng forklift.",
                "Maglakad sa mga markadong pasilyo at tumingin sa mata ng operator bago tumawid.",
                "Panatilihing mababa at matatag ang karga; huwag kailanman sumakay sa forks.",
            ],
            "close": "Kung hindi mo nakikita ang mata ng operator, hindi ka rin niya nakikita.",
        },
        "vi": {
            "title": "Xe nâng và con người",
            "why": "Người lái xe nâng thường không nhìn thấy người đi phía sau kiện hàng.",
            "points": [
                "Chỉ người đã được đào tạo và đánh giá mới được lái xe nâng.",
                "Đi trong lối đi có vạch kẻ và nhìn vào mắt người lái trước khi băng qua.",
                "Giữ hàng thấp và chắc; không bao giờ đứng lên càng nâng.",
            ],
            "close": "Nếu bạn không nhìn thấy mắt người lái, người lái cũng không thấy bạn.",
        },
        "ar": {
            "title": "الرافعات الشوكية والناس",
            "why": "كثيرًا ما لا يرى سائق الرافعة الشوكية شخصًا يمشي خلف الحمولة.",
            "points": [
                "لا يقود الرافعة الشوكية إلا السائقون المدرَّبون والمقيَّمون.",
                "امشِ في الممرات المحددة وتواصل بالعين مع السائق قبل العبور.",
                "أبقِ الحمولة منخفضة وثابتة؛ ولا تركب على الشوكتين أبدًا.",
            ],
            "close": "إذا لم ترَ عيني السائق، فهو لا يراك.",
        },
    },
}


def extra_language(value: Any) -> tuple[str, str]:
    """The one extra language a person picked, as a code; "" for English only.

    Accepts a code ("vi"), a label ("Vietnamese (vi)"), "None (English only)", nothing, or a
    list of one. Returns (code, problem); the problem is empty when the choice is valid.
    """
    if isinstance(value, (list, tuple)):
        picked = [v for v in value if str(v).strip()]
        if len(picked) > 1:
            return "", "Pick at most one language besides English."
        value = picked[0] if picked else ""
    text = str(value or "").strip()
    if not text or text.lower().startswith("none") or text.lower() in ("en", "english"):
        return "", ""
    code = text[text.rfind("(") + 1 : text.rfind(")")] if text.endswith(")") else text
    code = code.strip().lower()
    if code not in LANGUAGES:
        return "", f"{text} is not offered; choose one of {', '.join(LANGUAGES.values())}, or English only."
    return code, ""
