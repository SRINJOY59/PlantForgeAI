// Field Copilot localization. Two jobs:
//
//  1. LANGUAGES - the selector's options. `code` is what the backend and model
//     see; `speech` is the fuller BCP-47 tag with a region, which the browser's
//     speech engine matches voices against far better than a bare "hi" or "bn".
//
//  2. t(key, lang) - UI chrome strings (buttons, labels, placeholders). The
//     ANSWERS themselves are translated by the model server-side, so this table
//     only needs the shell. English is complete and is the fallback; other
//     languages fill in what they can and inherit the rest.
//
// Keep `code` values in sync with SUPPORTED_LANGUAGES in
// services/gateway/routes/field.py.

export const LANGUAGES = [
  { code: "en", label: "English",   speech: "en-US" },
  { code: "hi", label: "हिन्दी",     speech: "hi-IN" },
  { code: "bn", label: "বাংলা",      speech: "bn-IN" },
  { code: "ta", label: "தமிழ்",       speech: "ta-IN" },
  { code: "te", label: "తెలుగు",      speech: "te-IN" },
  { code: "mr", label: "मराठी",      speech: "mr-IN" },
  { code: "gu", label: "ગુજરાતી",    speech: "gu-IN" },
  { code: "kn", label: "ಕನ್ನಡ",      speech: "kn-IN" },
  { code: "ml", label: "മലയാളം",    speech: "ml-IN" },
  { code: "pa", label: "ਪੰਜਾਬੀ",     speech: "pa-IN" },
  { code: "or", label: "ଓଡ଼ିଆ",       speech: "or-IN" },
  { code: "as", label: "অসমীয়া",    speech: "as-IN" },
  { code: "ur", label: "اردو",       speech: "ur-IN" },
  { code: "es", label: "Español",   speech: "es-ES" },
  { code: "fr", label: "Français",  speech: "fr-FR" },
  { code: "de", label: "Deutsch",   speech: "de-DE" },
  { code: "ar", label: "العربية",    speech: "ar-SA" },
  { code: "zh", label: "中文",        speech: "zh-CN" },
  { code: "pt", label: "Português", speech: "pt-BR" },
];

// Languages a dispatched work order can actually be TRANSLATED into, as
// opposed to languages the copilot will answer in. The two lists differ: the
// model answers a question in anything, but a job card is only written in a
// language the dispatcher has a name and a script for, and offering an
// engineer a language their worker would then receive in English is worse than
// not offering it. Keep in step with LANGUAGE_NAMES in
// services/agents/usecases/work_order/dispatch.py.
export const DISPATCH_LANGUAGES = LANGUAGES.filter((l) =>
  ["en", "hi", "bn", "ta", "te", "mr", "gu", "kn", "ml", "pa", "or", "as", "ur"]
    .includes(l.code));

// The BCP-47 tag to hand the speech engine for a given language code.
export function speechLang(code) {
  return (LANGUAGES.find((l) => l.code === code) || LANGUAGES[0]).speech;
}

const STRINGS = {
  en: {
    title: "Field Copilot",
    pick_asset: "Pick an asset",
    all_assets: "All assets",
    ask_placeholder: "Ask about this asset…",
    ask_generic: "Ask anything about the plant…",
    listening: "Listening…",
    thinking: "Thinking…",
    speak: "Speak",
    stop: "Stop",
    send: "Send",
    tap_to_talk: "Tap to talk",
    live: "Live",
    no_alarms: "No standing alarms",
    standing_alarms: "Standing alarms",
    likely_causes: "Likely causes",
    language: "Language",
    scoped_to: "Scoped to",
    mic_denied: "Microphone permission denied",
    offline: "Can't reach the plant. Check your connection.",
    sign_out: "Sign out",
    tab_copilot: "Copilot",
    tab_ask: "Ask",
    tab_permit: "Permit",
    permit_pick_asset: "Which asset?",
    permit_describe: "Describe the job — what work, on what part…",
    permit_request: "Request permit",
    permit_drafting: "Drafting permit…",
    permit_gathering: "Checking the plant graph",
    permit_empty: "Pick an asset and describe the job to request a Permit-to-Work.",
    permit_failed: "Couldn't draft the permit. Try again.",
    permit_pending_auth: "This is a REQUEST, not a permit to start. A supervisor or engineer must review and sign it before any work begins. Do not start work on this alone.",
    permit_isolations: "Lock-out / Tag-out points",
    permit_hazards: "Hazards",
    permit_ppe: "Required PPE",
    permit_procedures: "Procedures to follow",
    permit_standards: "Governing standards",
    permit_none_isolation: "No isolation points found — confirm with your supervisor.",
    permit_none_hazard: "No hazards found in records — stay alert regardless.",
    permit_none_proc: "No specific procedure found.",

    tab_jobs: "My Jobs",
    jobs_title: "Work assigned to me",
    jobs_refresh: "Refresh",
    jobs_completed: "Completed",
    jobs_empty: "No work assigned",
    jobs_empty_hint: "Approved work orders from your engineer appear here, in your language.",
    job_safety: "Before you start",
    job_no_safety: "No isolation points or hazards were recorded for this job. Confirm with your supervisor before starting.",
    job_steps: "What to do",
    job_references: "Procedures and standards",
    job_accept: "Accept job",
    job_start: "Start work",
    job_done: "Mark complete",
    job_show_english: "Show English",
    job_show_mine: "Show my language",
    job_authorised_by: "Authorised by",
    job_status_assigned: "New",
    job_status_acknowledged: "Accepted",
    job_status_in_progress: "In progress",
    job_status_done: "Done",
  },
  hi: {
    title: "फील्ड कोपायलट",
    pick_asset: "उपकरण चुनें",
    all_assets: "सभी उपकरण",
    ask_placeholder: "इस उपकरण के बारे में पूछें…",
    ask_generic: "प्लांट के बारे में कुछ भी पूछें…",
    listening: "सुन रहा हूँ…",
    thinking: "सोच रहा हूँ…",
    speak: "बोलें",
    stop: "रोकें",
    send: "भेजें",
    tap_to_talk: "बोलने के लिए टैप करें",
    live: "लाइव",
    no_alarms: "कोई सक्रिय अलार्म नहीं",
    standing_alarms: "सक्रिय अलार्म",
    likely_causes: "संभावित कारण",
    language: "भाषा",
    scoped_to: "चयनित",
    mic_denied: "माइक्रोफ़ोन की अनुमति नहीं मिली",
    offline: "प्लांट से संपर्क नहीं हो पा रहा। कनेक्शन जांचें।",
    sign_out: "साइन आउट",
    tab_copilot: "कोपायलट",
    tab_ask: "पूछें",
    tab_permit: "परमिट",
    permit_pick_asset: "कौन सा उपकरण?",
    permit_describe: "काम बताएं — क्या काम, किस हिस्से पर…",
    permit_request: "परमिट का अनुरोध करें",
    permit_drafting: "परमिट तैयार हो रहा है…",
    permit_pending_auth: "यह एक अनुरोध है, काम शुरू करने की अनुमति नहीं। काम शुरू करने से पहले सुपरवाइज़र या इंजीनियर को इसे जांचकर हस्ताक्षर करना होगा। अकेले काम शुरू न करें।",
    permit_isolations: "लॉक-आउट / टैग-आउट बिंदु",
    permit_hazards: "खतरे",
    permit_ppe: "आवश्यक PPE",

    tab_jobs: "मेरे काम",
    jobs_title: "मुझे सौंपा गया काम",
    jobs_refresh: "रिफ्रेश करें",
    jobs_completed: "पूर्ण हुए",
    jobs_empty: "कोई काम नहीं सौंपा गया",
    jobs_empty_hint: "आपके इंजीनियर द्वारा मंजूर किए गए कार्य आदेश यहाँ आपकी भाषा में दिखेंगे।",
    job_safety: "शुरू करने से पहले",
    job_no_safety: "इस काम के लिए कोई आइसोलेशन या खतरा दर्ज नहीं है। शुरू करने से पहले अपने सुपरवाइज़र से पुष्टि करें।",
    job_steps: "क्या करना है",
    job_references: "प्रक्रियाएँ और मानक",
    job_accept: "काम स्वीकार करें",
    job_start: "काम शुरू करें",
    job_done: "पूर्ण चिह्नित करें",
    job_show_english: "अंग्रेज़ी में देखें",
    job_show_mine: "मेरी भाषा में देखें",
    job_authorised_by: "अनुमोदित कर्ता",
    job_status_assigned: "नया",
    job_status_acknowledged: "स्वीकृत",
    job_status_in_progress: "चल रहा है",
    job_status_done: "पूर्ण",
  },
  bn: {
    title: "ফিল্ড কোপাইলট",
    pick_asset: "যন্ত্র নির্বাচন করুন",
    all_assets: "সব যন্ত্র",
    ask_placeholder: "এই যন্ত্র সম্পর্কে জিজ্ঞাসা করুন…",
    ask_generic: "প্ল্যান্ট সম্পর্কে যেকোনো কিছু জিজ্ঞাসা করুন…",
    listening: "শুনছি…",
    thinking: "ভাবছি…",
    speak: "বলুন",
    stop: "থামান",
    send: "পাঠান",
    tap_to_talk: "কথা বলতে ট্যাপ করুন",
    live: "লাইভ",
    no_alarms: "কোনো সক্রিয় অ্যালার্ম নেই",
    standing_alarms: "সক্রিয় অ্যালার্ম",
    likely_causes: "সম্ভাব্য কারণ",
    language: "ভাষা",
    scoped_to: "নির্বাচিত",
    mic_denied: "মাইক্রোফোনের অনুমতি নেই",
    offline: "প্ল্যান্টে পৌঁছানো যাচ্ছে না। সংযোগ পরীক্ষা করুন।",
    sign_out: "সাইন আউট",
    tab_copilot: "কোপাইলট",
    tab_ask: "জিজ্ঞাসা",
    tab_permit: "পারমিট",
    permit_pick_asset: "কোন যন্ত্র?",
    permit_describe: "কাজটি বর্ণনা করুন — কী কাজ, কোন অংশে…",
    permit_request: "পারমিটের অনুরোধ করুন",
    permit_drafting: "পারমিট তৈরি হচ্ছে…",
    permit_pending_auth: "এটি একটি অনুরোধ, কাজ শুরু করার অনুমতি নয়। কাজ শুরুর আগে একজন সুপারভাইজার বা ইঞ্জিনিয়ারকে এটি পর্যালোচনা করে স্বাক্ষর করতে হবে। একা কাজ শুরু করবেন না।",
    permit_isolations: "লক-আউট / ট্যাগ-আউট পয়েন্ট",
    permit_hazards: "বিপদ",
    permit_ppe: "প্রয়োজনীয় PPE",

    tab_jobs: "আমার কাজ",
    jobs_title: "আমাকে দেওয়া কাজ",
    jobs_refresh: "রিফ্রেশ করুন",
    jobs_completed: "সম্পন্ন",
    jobs_empty: "কোনো কাজ দেওয়া হয়নি",
    jobs_empty_hint: "আপনার ইঞ্জিনিয়ারের অনুমোদিত কাজের আদেশ এখানে আপনার ভাষায় দেখাবে।",
    job_safety: "শুরু করার আগে",
    job_no_safety: "এই কাজের জন্য কোনো আইসোলেশন বা বিপদ লিপিবদ্ধ নেই। শুরুর আগে সুপারভাইজারের সঙ্গে নিশ্চিত হন।",
    job_steps: "কী করতে হবে",
    job_references: "পদ্ধতি ও মান",
    job_accept: "কাজ গ্রহণ করুন",
    job_start: "কাজ শুরু করুন",
    job_done: "সম্পন্ন চিহ্নিত করুন",
    job_show_english: "ইংরেজিতে দেখুন",
    job_show_mine: "আমার ভাষায় দেখুন",
    job_authorised_by: "অনুমোদন করেছেন",
    job_status_assigned: "নতুন",
    job_status_acknowledged: "গৃহীত",
    job_status_in_progress: "চলছে",
    job_status_done: "সম্পন্ন",
  },
};

/** UI chrome string for `key` in `lang`, falling back to English. */
export function t(key, lang = "en") {
  const table = STRINGS[lang] || STRINGS.en;
  return table[key] ?? STRINGS.en[key] ?? key;
}
