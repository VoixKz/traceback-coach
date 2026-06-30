"""Internationalisation data for traceback-coach.

Provides:
- FAMILIES_ZH: the 12 ErrorFamily entries translated to Traditional Chinese
  (zh-HK, Standard Written Chinese as used in Hong Kong).
- LABELS: UI strings for "en" and "zh" keyed exactly as required by the card
  renderer.

No IPython import. All prose fields are translated; example_code is kept
verbatim from the English source. Error-type names (NameError, TypeError …)
and code identifiers are kept in English inside the prose.
"""
from __future__ import annotations

from .knowledge import ErrorFamily, FAMILIES

# ---------------------------------------------------------------------------
# zh-HK translated knowledge families
# ---------------------------------------------------------------------------

FAMILIES_ZH: dict[str, ErrorFamily] = {
    "NameError": ErrorFamily(
        key="NameError",
        translation="Python 不認識名稱 `{token}` — 它從未被賦值，或者是拼寫錯誤。",
        family_summary="你使用了一個 Python 從未見過的名稱。",
        read_it_yourself="最後一行寫著 `name '...' is not defined` — 那個名稱就是問題所在。",
        cause_phrase="名稱 `{token}` 從未被定義",
        example_code=FAMILIES["NameError"].example_code,
        example_explanation="Python 讀取 `total`，找不到任何同名的變數，於是停止執行。",
        example_avoid="在使用變數之前，先建立並賦值給它；同時檢查拼寫和大小寫是否正確。",
        question_template="在你的程式碼中，`{token}` 是在哪裡第一次獲得值的？",
    ),
    "TypeError": ErrorFamily(
        key="TypeError",
        translation="你把不相容類型的值混在一起使用了：{message}",
        family_summary="某個操作收到了它無法處理的類型（例如 str + int）。",
        read_it_yourself="錯誤訊息會指出衝突所在 — 留意 'unsupported operand' 或 'expected ...' 等字眼。",
        cause_phrase="操作中存在不相容的類型",
        example_code=FAMILIES["TypeError"].example_code,
        example_explanation="`age` 是字串（'5'），所以把數字 1 加上去對 Python 而言毫無意義。",
        example_avoid="先進行轉換，例如 int(age) + 1，或確保兩邊的類型一致。",
        question_template="失敗那一行上兩個值的類型分別是什麼？",
    ),
    "ValueError": ErrorFamily(
        key="ValueError",
        translation="類型是對的，但值不被接受：{message}",
        family_summary="種類正確，內容卻有問題（例如 int('abc')）。",
        read_it_yourself="錯誤訊息會引用出問題的值 — 看看你傳入了什麼。",
        cause_phrase="這個值在此處不被接受",
        example_code=FAMILIES["ValueError"].example_code,
        example_explanation="`int()` 接受字串，但只接受看起來像整數的字串。",
        example_avoid="在轉換之前，先驗證或清理這個值。",
        question_template="到達這一行時，確切的值是什麼？它是這個函數所期望的格式嗎？",
    ),
    "IndexError": ErrorFamily(
        key="IndexError",
        translation="你要求的位置在序列中不存在：{message}",
        family_summary="索引超出範圍（通常是差一錯誤）。",
        read_it_yourself="'list index out of range' 表示那個位置根本不存在。",
        cause_phrase="索引超過了序列的末端",
        example_code=FAMILIES["IndexError"].example_code,
        example_explanation="長度為 3 的列表，索引為 0 至 2；索引 3 已超出末端一位。",
        example_avoid="索引從 0 開始；最後一個有效索引是 len(xs) - 1。",
        question_template="這個序列有多長？最大的有效索引是多少？",
    ),
    "KeyError": ErrorFamily(
        key="KeyError",
        translation="鍵 `{token}` 不在字典中。",
        family_summary="你查詢了一個字典中不存在的鍵。",
        read_it_yourself="'KeyError:' 後面緊跟著那個找不到的鍵。",
        cause_phrase="鍵 `{token}` 不在字典中",
        example_code=FAMILIES["KeyError"].example_code,
        example_explanation="`d` 只有鍵 'a'，所以查詢 'b' 會失敗。",
        example_avoid="用 `key in d` 先確認，或使用 d.get(key) 取得安全的預設值。",
        question_template="字典目前實際包含哪些鍵？",
    ),
    "AttributeError": ErrorFamily(
        key="AttributeError",
        translation="那個物件沒有 `{token}`：{message}",
        family_summary="該物件沒有那個方法或屬性。",
        read_it_yourself="'... object has no attribute ...' 會指出類型和缺失的屬性名稱。",
        cause_phrase="物件沒有屬性 `{token}`",
        example_code=FAMILIES["AttributeError"].example_code,
        example_explanation="字串是不可變的，沒有 `append` 方法；那是列表的方法。",
        example_avoid="確認物件的實際類型，以及該類型支援哪些方法。",
        question_template="那個物件是什麼類型？該類型有 `{token}` 嗎？",
    ),
    "IndentationError": ErrorFamily(
        key="IndentationError",
        translation="縮排（行首的空格）不正確：{message}",
        family_summary="Python 用縮排來分組程式碼，但縮排沒有對齊。",
        read_it_yourself="Python 的插入符號（^）會指出縮排出錯的位置。",
        cause_phrase="縮排未對齊",
        example_code=FAMILIES["IndentationError"].example_code,
        example_explanation="def/if/for 的主體必須在其標頭下方縮排。",
        example_avoid="保持一致的縮排（4 個空格）；絕不混用 Tab 和空格。",
        question_template="這一行應該屬於哪個程式碼塊，它是否在該塊的下方縮排了？",
    ),
    "SyntaxError": ErrorFamily(
        key="SyntaxError",
        translation="Python 無法將這一行解讀為有效的程式碼：{message}",
        family_summary="程式碼違反了 Python 的語法規則（缺少 ':' 、')' 、引號……）。",
        read_it_yourself="插入符號（^）標記了 Python 感到困惑的位置；請檢查它前面的內容。",
        cause_phrase="這在此處不是有效的 Python 語法",
        example_code=FAMILIES["SyntaxError"].example_code,
        example_explanation="`if` 的標頭必須以冒號 `:` 結尾。",
        example_avoid="檢查標記位置附近是否缺少冒號、括號或引號。",
        question_template="看看 ^ 符號前面 — 可能缺少了什麼標點符號？",
    ),
    "ZeroDivisionError": ErrorFamily(
        key="ZeroDivisionError",
        translation="你除以了零，這個運算沒有結果。",
        family_summary="除法或取餘數時，除數為零。",
        read_it_yourself="'division by zero' 表示執行時除數的值是 0。",
        cause_phrase="除數為 0",
        example_code=FAMILIES["ZeroDivisionError"].example_code,
        example_explanation="除以零在數學上沒有定義，所以 Python 停止執行。",
        example_avoid="在進行除法之前，先確認除數不為 0。",
        question_template="這一行執行時，除數的值是什麼？",
    ),
    "ModuleNotFoundError": ErrorFamily(
        key="ModuleNotFoundError",
        translation="Python 找不到要匯入的模組 `{token}`。",
        family_summary="匯入的名稱未安裝，或存在拼寫錯誤。",
        read_it_yourself="\"No module named '...'\" 會精確指出找不到的模組名稱。",
        cause_phrase="找不到模組 `{token}`",
        example_code=FAMILIES["ModuleNotFoundError"].example_code,
        example_explanation="Python 搜尋已安裝的套件，卻找不到任何同名的模組。",
        example_avoid="確認拼寫是否正確，以及套件是否已在這個核心環境中安裝。",
        question_template="`{token}` 的拼寫正確嗎？它是否已在這個核心環境中安裝？",
    ),
    "RecursionError": ErrorFamily(
        key="RecursionError",
        translation="函數不斷呼叫自身，卻沒有任何停止條件。",
        family_summary="遞迴從未到達基本情況（base case）。",
        read_it_yourself="'maximum recursion depth exceeded' 表示無限的自我呼叫。",
        cause_phrase="遞迴沒有基本情況來停止",
        example_code=FAMILIES["RecursionError"].example_code,
        example_explanation="`f` 永遠呼叫 `f`；沒有任何一條路徑可以不遞迴地回傳。",
        example_avoid="添加一個能在繼續遞迴之前回傳的基本情況，並確保每次呼叫都在向它靠近。",
        question_template="什麼條件應該停止遞迴？這個條件是否真的能被觸發？",
    ),
    "UnboundLocalError": ErrorFamily(
        key="UnboundLocalError",
        translation="在這個函數內部，`{token}` 在被賦值之前就被使用了。",
        family_summary="一個區域變數在賦值前被讀取（通常是遮蔽了全域變數）。",
        read_it_yourself="\"local variable '...' referenced before assignment\" 會指出那個變數名稱。",
        cause_phrase="區域變數 `{token}` 在賦值前被使用",
        example_code=FAMILIES["UnboundLocalError"].example_code,
        example_explanation="在 `inc` 函數內部對 `count` 進行賦值，使它成為區域變數，因此右側的 `count` 尚無值。",
        example_avoid="將值作為參數傳入，或明確使用 `global` 或 `nonlocal` 宣告。",
        question_template="在函數內部，`{token}` 是在哪裡第一次獲得值的，是否在被使用之前？",
    ),
}

# ---------------------------------------------------------------------------
# UI label strings
# ---------------------------------------------------------------------------

LABELS: dict[str, dict[str, str]] = {
    "en": {
        # The values below are copied verbatim from render_card_html / magics so
        # that the English output path is byte-identical to the current code.
        "coach": "🧭 Coach",
        "what_happened": "What happened:",
        "why_breaks": "Why it breaks:",
        "where": "Where:",
        "family_read": "Read it yourself:",
        "see_example": "See this error on a small example",
        "avoid_next": "Avoid it next time:",
        "question": "Question:",
        "seen_min": " — you've seen this one; read it yourself.",
        "guess_first": (
            "🤔 <strong>Guess first:</strong> what <em>type</em> of error do you think "
            "this is (NameError? TypeError? IndexError? …)? Predict it, then reveal."
        ),
        "reveal": "👁️ Reveal the Coach's analysis",
        "fixed_it": (
            "✅ <strong>Fixed it!</strong> The cell that was failing now runs clean. "
            "What did you change, and why did it work?"
        ),
    },
    "zh": {
        "coach": "🧭 教練",
        "what_happened": "發生了什麼：",
        "why_breaks": "為何出錯：",
        "where": "位置：",
        "family_read": "自行閱讀：",
        "see_example": "看看這個錯誤的小範例",
        "avoid_next": "下次如何避免：",
        "question": "問題：",
        "seen_min": " — 你已見過這個錯誤；請自行閱讀錯誤訊息。",
        "guess_first": (
            "🤔 <strong>先猜猜看：</strong>你認為這是哪種<em>類型</em>的錯誤"
            "（NameError？TypeError？IndexError？……）？先預測，再揭曉答案。"
        ),
        "reveal": "👁️ 揭曉教練的分析",
        "fixed_it": (
            "✅ <strong>修好了！</strong>之前出錯的儲存格現在可以正常執行了。"
            "你改了什麼？為什麼這樣修就能解決問題？"
        ),
    },
}
