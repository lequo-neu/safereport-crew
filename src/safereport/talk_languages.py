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
    "vi": "Các cơ sở sản xuất tương tự đã báo cáo {{topic_reports}} trường hợp chấn thương nghiêm trọng thuộc nhóm này kể từ năm {{since}}.",
    "ar": "منذ عام {{since}}، أبلغت مصانع مماثلة لمصنعكم عن إصابات خطيرة من هذا النوع، وبلغ إجمالي عدد الإصابات {{topic_reports}}.",
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
            "title": "Khóa và gắn thẻ cảnh báo trước khi can thiệp vào máy",
            "why": "Máy có thể khởi động bất ngờ. Khi gỡ kẹt, vệ sinh hoặc điều chỉnh, "
            "tay có thể tiếp xúc với các bộ phận đang chuyển động.",
            "points": [
                (
                    "Dừng máy, cô lập mọi nguồn năng lượng và xử lý an toàn năng lượng tích trữ: "
                    "điện, khí nén, thủy lực, trọng lực và lò xo."
                ),
                "Gắn khóa cá nhân và thẻ cảnh báo tại các điểm cách ly theo quy trình khóa/gắn thẻ (LOTO).",
                (
                    "Sau khi cô lập và xử lý năng lượng tích trữ, xác minh máy không thể khởi động; "
                    "đưa bộ điều khiển về vị trí tắt trước khi làm việc."
                ),
                (
                    "Nếu máy thường xuyên bị kẹt, báo người giám sát; "
                    "không gỡ kẹt khi máy chưa được cô lập an toàn."
                ),
            ],
            "close": "Trước khi thao tác, hãy kiểm tra: còn nguồn năng lượng nào có thể khiến máy chuyển động không?",
        },
        "ar": {
            "title": "اعزل الطاقة وأقفلها قبل أن تمد يدك",
            "why": "قد تبدأ الآلات بالعمل دون سابق إنذار. وعند إزالة انحشار أو التنظيف أو إجراء ضبط سريع، تمتد الأيدي إلى المكان الذي كان يحميه الواقي.",
            "points": [
                "أوقف الآلة واعزل جميع مصادر الطاقة: الكهربائية والهوائية والهيدروليكية والجاذبية والطاقة المخزّنة في النوابض.",
                "ضع قفلك الشخصي وبطاقة التحذير الخاصة بك على كل نقطة عزل. القفل قفلك، والمفتاح مفتاحك.",
                "بعد عزل جميع مصادر الطاقة وإقفالها، ابقَ بعيدًا عن الأجزاء الخطرة وحاول تشغيل الآلة من أدوات التحكم المعتادة للتأكد من أنها لا تعمل، ثم أعد أدوات التحكم إلى وضع الإيقاف قبل أن تمد يدك.",
                "إذا تكرر الانحشار فأبلغ مشرفك، ولا تحاول إزالته والآلة تعمل.",
            ],
            "close": "اسأل نفسك: هل بقيت أي طاقة يمكن أن تحرك هذه الآلة؟ إن لم تكن متأكدًا، فالآلة لم تُعزل ولم تُقفل بعد.",
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
            "title": "Giữ bộ phận che chắn của máy đúng vị trí",
            "why": "Trục cán, lưỡi dao và dây đai có thể cuốn găng tay hoặc tay áo "
            "trước khi người vận hành kịp phản ứng.",
            "points": [
                "Không vận hành máy khi bộ phận che chắn bị tháo, hư hỏng hoặc bị vô hiệu hóa.",
                "Giữ tay tránh xa vùng gia công; sử dụng que đẩy và dụng cụ cấp phôi phù hợp.",
                "Báo ngay bộ phận che chắn bị thiếu hoặc hỏng trước khi bắt đầu ca làm việc.",
            ],
            "close": "Nếu bộ phận che chắn gây vướng, báo người giám sát; "
            "không tự ý tháo hay bỏ qua để làm nhanh.",
        },
        "ar": {
            "title": "أبقِ حواجز الحماية في مكانها",
            "why": "تسحب البكرات والشفرات والسيور القفاز أو الكُمّ إلى الداخل أسرع من أن يتمكن أي شخص من رد الفعل.",
            "points": [
                "لا تشغّل أي آلة أبدًا إذا كان حاجز الحماية منزوعًا أو مثنيًا أو معطَّلًا أو تم تجاوزه.",
                "أبعد يديك عن نقطة التشغيل، واستخدم عصي الدفع وأدوات التغذية.",
                "أبلغ عن أي حاجز حماية مفقود أو تالف قبل بدء الوردية.",
            ],
            "close": "إذا كان حاجز الحماية يبطئ العمل فأبلغ عن ذلك؛ فنزعه ليس هو الحل.",
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
            "title": "Phòng ngã tại mép sàn và khu vực trên cao",
            "why": "Nguy cơ ngã có thể xuất hiện cả trong công việc quen thuộc: "
            "bước lên rơ-moóc hoặc làm việc gần mép sàn lửng.",
            "points": [
                (
                    "Chỉ làm việc ở mép sàn khi có biện pháp chống ngã phù hợp với công việc; "
                    "không bước qua khu vực không được bảo vệ."
                ),
                "Che chắn và đánh dấu rõ các lỗ mở trên sàn và ô lấy sáng trên mái.",
                "Giữ ba điểm tiếp xúc khi lên xuống thang hoặc bậc lên xuống thiết bị.",
            ],
            "close": "Trước khi lên cao, hãy xác định: nếu trượt chân, biện pháp nào sẽ bảo vệ bạn?",
        },
        "ar": {
            "title": "كل حافة غير محمية قد تشكّل خطرًا للسقوط",
            "why": "تقع معظم حالات السقوط أثناء أعمال قصيرة واعتيادية: خطوة واحدة إلى ظهر مقطورة، أو نظرة سريعة من فوق حافة طابق نصفي (ميزانين).",
            "points": [
                "استخدم الدرابزين أو حزام الجسم الكامل للحماية من السقوط أو منصة العمل المرتفعة، ولا تتجاوز أبدًا حافة غير محمية.",
                "غطِّ الفتحات وفتحات الإضاءة السقفية، وضع عليها علامات واضحة.",
                "حافظ على ثلاث نقاط ارتكاز عند الصعود إلى المعدات والنزول منها.",
            ],
            "close": "قبل أن تصعد، اسأل نفسك: ما الذي سيحميني إذا انزلقت؟",
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
            "why": "Người vận hành xe nâng có thể không nhìn thấy người đi bộ bị khuất sau hàng hóa.",
            "points": [
                "Chỉ người đã được đào tạo, đánh giá và cho phép mới được vận hành xe nâng.",
                (
                    "Đi đúng lối dành cho người đi bộ; chỉ băng qua khi người lái "
                    "đã nhìn thấy bạn và xác nhận nhường đường."
                ),
                (
                    "Giữ hàng thấp và ổn định khi di chuyển; "
                    "không đứng trên càng nâng hoặc dưới tải đang nâng."
                ),
            ],
            "close": "Nếu tầm nhìn bị che khuất, hãy dừng lại và giữ khoảng cách; "
            "đừng đoán rằng người lái đã nhìn thấy mình.",
        },
        "ar": {
            "title": "الرافعات الشوكية والمشاة",
            "why": "كثيرًا ما لا يستطيع مشغّل الرافعة الشوكية رؤية شخص يسير خلف الحمولة.",
            "points": [
                "لا يقود الرافعة الشوكية إلا المشغّلون الذين أتمّوا التدريب واجتازوا التقييم.",
                "امشِ في الممرات المحددة بعلامات، وتبادل النظر مع المشغّل قبل العبور.",
                "أبقِ الحمولة منخفضة ومستقرة، ولا تركب على الشوكتين أبدًا.",
            ],
            "close": "إذا لم ترَ عيني المشغّل، فهو لا يراك.",
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
