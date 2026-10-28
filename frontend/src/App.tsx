import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent,
} from "react";
import { FamilyDashboard } from "./FamilyDashboard";
import { ColoringActivity } from "./ColoringActivity";
import { TextbookQuiz } from "./TextbookQuiz";
import { VoiceControls } from "./VoiceControls";
import { getApiBaseUrl } from "./learningTypes";
import { subjectsFor, textbookMediumForSubject } from "./subjectCatalog";
import type { FamilyUser, Locale, Student } from "./learningTypes";

type Page = "home" | "tutor" | "coloring" | "practice" | "progress" | "family";
type ApiStatus = "checking" | "online" | "offline";
type Source = {
  textbook_id: string;
  textbook_title: string | null;
  source_file: string;
  pdf_page_number: number;
  chapter: string | null;
  lesson: string | null;
  source_official_status: string;
  chunk_id: string;
};
type AnswerAction = "translate" | "explain" | "short";
type AnswerTransformation = {
  action: AnswerAction;
  language: Locale;
  text: string;
};
type ChatMessage = {
  id: number;
  role: "student" | "tutor";
  text: string;
  status?: "grounded" | "general" | "abstained";
  sources?: Source[];
  question?: string;
  grade?: number;
  subject?: string;
  medium?: Locale;
  answerLanguage?: Locale;
  transformations?: AnswerTransformation[];
};

function isSource(value: unknown): value is Source {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  return (
    "textbook_id" in value &&
    typeof value.textbook_id === "string" &&
    "textbook_title" in value &&
    (typeof value.textbook_title === "string" || value.textbook_title === null) &&
    "source_file" in value &&
    typeof value.source_file === "string" &&
    "pdf_page_number" in value &&
    typeof value.pdf_page_number === "number" &&
    "chapter" in value &&
    (typeof value.chapter === "string" || value.chapter === null) &&
    "lesson" in value &&
    (typeof value.lesson === "string" || value.lesson === null) &&
    "source_official_status" in value &&
    typeof value.source_official_status === "string" &&
    "chunk_id" in value &&
    typeof value.chunk_id === "string"
  );
}

function isLearningAnswer(
  value: unknown,
): value is {
  answer: string;
  status: "grounded" | "general" | "abstained";
  sources: Source[];
} {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  return (
    "answer" in value &&
    typeof value.answer === "string" &&
    "status" in value &&
    (value.status === "grounded" || value.status === "general" || value.status === "abstained") &&
    "sources" in value &&
    Array.isArray(value.sources) &&
    value.sources.every(isSource)
  );
}

const copy: Record<Locale, Record<string, string>> = {
  English: {
    brand: "SL Scholar AI",
    tagline: "Curious minds grow here",
    switchToDarkMode: "Switch to dark mode",
    switchToLightMode: "Switch to light mode",
    home: "Home",
    tutor: "Ask my tutor",
    coloringNav: "Colour",
    practice: "Activities",
    progress: "My progress",
    gradeOption: "Grade",
    regionGrade: "GRADE 1–5 · SRI LANKA",
    exploreEyebrow: "LET’S LEARN",
    tutorEyebrow: "YOUR TEXTBOOK HELPER",
    composerHint: "Enter to send · Shift+Enter for a new line",
    sidebarFooter: "Made for curious learners · Grades 1–5",
    welcome: "Hello, learner!",
    welcomeText: "What would you like to learn today?",
    grade: "My grade",
    textbookLanguage: "Textbook language",
    sourceLanguageNote: "English shows all available subjects. For subjects without an English book, the tutor uses the available textbook language. Tamil is preferred when both Tamil and Sinhala books exist.",
    answerLanguage: "Answer language",
    subjects: "Explore your subjects",
    subjectHelp: "Choose a subject from the books in your selected language.",
    ask: "Ask the AI tutor",
    question: "Type your question here...",
    send: "Send question",
    tutorWelcome: "Hi! I can help you learn from your textbook.",
    tutorHelp: "Choose your grade, book language and subject, then ask a question.",
    source: "Textbook source",
    page: "PDF page",
    chapter: "Chapter",
    lesson: "Lesson",
    verified: "Answer based on textbook evidence",
    generalAnswer: "General answer — not found in the selected textbook",
    abstained: "I could not find enough textbook evidence for this answer.",
    retry: "Try again",
    clear: "New chat",
    clearConfirm: "Clear this conversation?",
    loading: "Looking in your textbook...",
    apiOnline: "Tutor service is connected",
    apiChecking: "Connecting to the tutor...",
    apiOffline: "Tutor service is offline. Start the backend to ask questions.",
    activitiesTitle: "Learning activities",
    progressTitle: "Your learning progress",
    progressPending: "Progress will appear here when secure student accounts and activity tracking are added.",
    emptyTitle: "Your learning journey starts here",
    emptyText: "Your chats are not saved yet. Ask a question to get started.",
    noSubjects: "No subjects are listed for this grade and book language.",
    sourceNote: "Page numbers refer to PDF pages. Book details appear only when available.",
    answerActions: "Answer options",
    translateTo: "Translate to",
    moreExplanation: "More explanation",
    shortAnswer: "Short answer",
    transformationFailed: "Sorry, that answer could not be updated. Please try again.",
    translating: "Translating...",
    explaining: "Explaining...",
    shortening: "Making it shorter...",
    translatedAnswer: "Translated to",
    errorPrefix: "I could not get an answer.",
    tryAgain: "Please try again in a moment.",
    tutorBusy: "The tutor is temporarily busy. Please try again shortly.",
    parentTeacher: "Open the secure parent and teacher dashboard.",
    regionNav: "Main navigation",
    regionChat: "Tutor conversation",
    status: "Service status",
    selected: "Selected",
  },
  Sinhala: {
    brand: "SL Scholar AI",
    tagline: "කුතුහලයෙන් දැනුමට",
    switchToDarkMode: "අඳුරු තේමාවට මාරු වන්න",
    switchToLightMode: "ආලෝක තේමාවට මාරු වන්න",
    home: "මුල් පිටුව",
    tutor: "ගුරු මිතුරාගෙන් අසන්න",
    coloringNav: "වර්ණ",
    practice: "ක්‍රියාකාරකම්",
    progress: "මගේ ප්‍රගතිය",
    gradeOption: "ශ්‍රේණිය",
    regionGrade: "ශ්‍රේණි 1–5 · ශ්‍රී ලංකාව",
    exploreEyebrow: "අපි ඉගෙනගනිමු",
    tutorEyebrow: "ඔබේ පෙළපොත් ගුරු මිතුරා",
    composerHint: "යැවීමට Enter · නව පේළියකට Shift+Enter",
    sidebarFooter: "කුතුහලයෙන් ඉගෙනගන්න · ශ්‍රේණි 1–5",
    welcome: "ආයුබෝවන්, පුංචි ඉගෙනුම් මිතුරා!",
    welcomeText: "අද ඔබ ඉගෙනගන්න කැමති කුමක්ද?",
    grade: "මගේ ශ්‍රේණිය",
    textbookLanguage: "පෙළපොතේ භාෂාව",
    sourceLanguageNote: "English තෝරාගත් විට ඇති සියලුම විෂයන් පෙන්වයි. English පොතක් නැති විෂයකට ඇති පෙළපොත් භාෂையை භාවිතා කරයි. Tamil සහ Sinhala දෙකම තිබේ නම් Tamil තෝරයි.",
    answerLanguage: "පිළිතුරු භාෂාව",
    subjects: "විෂයයන් තෝරන්න",
    subjectHelp: "තෝරාගත් භාෂාවේ පොත්වල ඇති විෂයයක් තෝරන්න.",
    ask: "AI ගුරු මිතුරාගෙන් අසන්න",
    question: "ඔබේ ප්‍රශ්නය මෙහි ලියන්න...",
    send: "ප්‍රශ්නය යවන්න",
    tutorWelcome: "ආයුබෝවන්! ඔබේ පෙළපොතෙන් ඉගෙනගන්න මම උදව් කරන්නම්.",
    tutorHelp: "ශ්‍රේණිය, පෙළපොතේ භාෂාව සහ විෂය තෝරා ප්‍රශ්නයක් අසන්න.",
    source: "පෙළපොත් මූලාශ්‍රය",
    page: "PDF පිටුව",
    chapter: "පරිච්ඡේදය",
    lesson: "පාඩම",
    verified: "පෙළපොත් සාක්ෂි මත පදනම් වූ පිළිතුර",
    generalAnswer: "සාමාන්‍ය පිළිතුරක් — තෝරාගත් පෙළපොතේ හමු නොවීය",
    abstained: "මෙයට පිළිතුරු දීමට ප්‍රමාණවත් පෙළපොත් සාක්ෂි හමු වුණේ නැහැ.",
    retry: "නැවත උත්සාහ කරන්න",
    clear: "අලුත් සංවාදය",
    clearConfirm: "මෙම සංවාදය මකන්නද?",
    loading: "පෙළපොතේ සොයමින්...",
    apiOnline: "ගුරු සේවාව සම්බන්ධ වී ඇත",
    apiChecking: "ගුරු සේවාවට සම්බන්ධ වෙමින්...",
    apiOffline: "ගුරු සේවාව සම්බන්ධ නැහැ. ප්‍රශ්න ඇසීමට backend ආරම්භ කරන්න.",
    activitiesTitle: "ඉගෙනුම් ක්‍රියාකාරකම්",
    progressTitle: "ඔබේ ඉගෙනුම් ප්‍රගතිය",
    progressPending: "ආරක්ෂිත ශිෂ්‍ය ගිණුම් සහ ක්‍රියාකාරකම් සටහන් එකතු කළ විට ප්‍රගතිය මෙහි පෙන්වයි.",
    emptyTitle: "ඔබේ ඉගෙනුම් ගමන මෙතැනින් ඇරඹේ",
    emptyText: "ඔබේ සංවාද තවම සුරැකෙන්නේ නැහැ. ආරම්භ කිරීමට ප්‍රශ්නයක් අසන්න.",
    noSubjects: "මෙම ශ්‍රේණියට සහ පෙළපොත් භාෂාවට විෂය ලැයිස්තුවක් නැහැ.",
    sourceNote: "පිටු අංක PDF පිටු සඳහාය. ලබාගත හැකි පොත් විස්තර පමණක් පෙන්වයි.",
    answerActions: "පිළිතුරු විකල්ප",
    translateTo: "පරිවර්තනය කරන්න",
    moreExplanation: "තවත් පැහැදිලි කරන්න",
    shortAnswer: "කෙටි පිළිතුර",
    transformationFailed: "කණගාටුයි, පිළිතුර වෙනස් කළ නොහැකියි. නැවත උත්සාහ කරන්න.",
    translating: "පරිවර්තනය කරමින්...",
    explaining: "පැහැදිලි කරමින්...",
    shortening: "කෙටි කරමින්...",
    translatedAnswer: "පරිවර්තනය කළ භාෂාව",
    errorPrefix: "පිළිතුර ලබාගත නොහැකි විය.",
    tryAgain: "කරුණාකර මොහොතකින් නැවත උත්සාහ කරන්න.",
    tutorBusy: "ගුරු සේවාව තාවකාලිකව කාර්යබහුලයි. ටික වේලාවකින් නැවත උත්සාහ කරන්න.",
    parentTeacher: "දෙමාපිය සහ ගුරු පුවරුව විවෘත කරන්න.",
    regionNav: "ප්‍රධාන මෙනුව",
    regionChat: "ගුරු මිතුරා සමඟ සංවාදය",
    status: "සේවා තත්ත්වය",
    selected: "තෝරා ඇත",
  },
  Tamil: {
    brand: "SL Scholar AI",
    tagline: "ஆர்வத்துடன் கற்போம்",
    switchToDarkMode: "இருண்ட பயன்முறைக்கு மாறு",
    switchToLightMode: "ஒளி பயன்முறைக்கு மாறு",
    home: "முகப்பு",
    tutor: "ஆசிரியரிடம் கேள்",
    coloringNav: "வண்ணம்",
    practice: "செயல்பாடுகள்",
    progress: "என் முன்னேற்றம்",
    gradeOption: "வகுப்பு",
    regionGrade: "வகுப்பு 1–5 · இலங்கை",
    exploreEyebrow: "கற்போம்",
    tutorEyebrow: "உன் பாடநூல் உதவியாளர்",
    composerHint: "அனுப்ப Enter · புதிய வரிக்கு Shift+Enter",
    sidebarFooter: "ஆர்வத்துடன் கற்போம் · வகுப்புகள் 1–5",
    welcome: "வணக்கம், மாணவரே!",
    welcomeText: "இன்று என்ன கற்க விரும்புகிறாய்?",
    grade: "என் வகுப்பு",
    textbookLanguage: "பாடநூல் மொழி",
    sourceLanguageNote: "English தேர்ந்தெடுத்தால் கிடைக்கும் எல்லாப் பாடங்களும் காட்டப்படும். English புத்தகம் இல்லாத பாடத்திற்கு கிடைக்கும் பாடநூல் மொழி பயன்படுத்தப்படும். Tamil, Sinhala இரண்டும் இருந்தால் Tamil முன்னுரிமை.",
    answerLanguage: "பதில் மொழி",
    subjects: "பாடங்களைத் தேர்ந்தெடு",
    subjectHelp: "தேர்ந்தெடுத்த மொழிப் புத்தகங்களில் உள்ள பாடத்தைத் தேர்ந்தெடு.",
    ask: "AI ஆசிரியரிடம் கேள்",
    question: "உன் கேள்வியை இங்கே எழுது...",
    send: "கேள்வியை அனுப்பு",
    tutorWelcome: "வணக்கம்! உன் பாடநூலிலிருந்து கற்க உதவுகிறேன்.",
    tutorHelp: "வகுப்பு, பாடநூல் மொழி, பாடத்தைத் தேர்ந்தெடுத்து கேள்வி கேள்.",
    source: "பாடநூல் மூலம்",
    page: "PDF பக்கம்",
    chapter: "அத்தியாயம்",
    lesson: "பாடம்",
    verified: "பாடநூல் ஆதாரத்தின் அடிப்படையிலான பதில்",
    generalAnswer: "பொதுவான பதில் — தேர்ந்தெடுத்த பாடநூலில் இல்லை",
    abstained: "இதற்குப் பதிலளிக்கப் போதுமான பாடநூல் ஆதாரம் கிடைக்கவில்லை.",
    retry: "மீண்டும் முயற்சி",
    clear: "புதிய உரையாடல்",
    clearConfirm: "இந்த உரையாடலை அழிக்கவா?",
    loading: "பாடநூலில் தேடுகிறது...",
    apiOnline: "ஆசிரியர் சேவை இணைக்கப்பட்டுள்ளது",
    apiChecking: "ஆசிரியர் சேவையுடன் இணைகிறது...",
    apiOffline: "ஆசிரியர் சேவை இணைக்கப்படவில்லை. கேள்வி கேட்க backend-ஐ தொடங்கவும்.",
    activitiesTitle: "கற்றல் செயல்பாடுகள்",
    progressTitle: "உன் கற்றல் முன்னேற்றம்",
    progressPending: "பாதுகாப்பான மாணவர் கணக்குகளும் செயல்பாட்டு பதிவுகளும் சேர்க்கப்பட்டால் முன்னேற்றம் இங்கே தோன்றும்.",
    emptyTitle: "உன் கற்றல் பயணம் இங்கே தொடங்குகிறது",
    emptyText: "உரையாடல்கள் இன்னும் சேமிக்கப்படுவதில்லை. தொடங்க ஒரு கேள்வி கேள்.",
    noSubjects: "இந்த வகுப்பு மற்றும் பாடநூல் மொழிக்கு பாடங்கள் பட்டியலிடப்படவில்லை.",
    sourceNote: "பக்க எண்கள் PDF பக்கங்களைக் குறிக்கும். கிடைக்கும் புத்தக விவரங்கள் மட்டுமே காட்டப்படும்.",
    answerActions: "பதில் விருப்பங்கள்",
    translateTo: "மொழிபெயர்",
    moreExplanation: "இன்னும் விளக்கு",
    shortAnswer: "சுருக்கமான பதில்",
    transformationFailed: "மன்னிக்கவும், பதிலை மாற்ற முடியவில்லை. மீண்டும் முயற்சி செய்.",
    translating: "மொழிபெயர்க்கிறது...",
    explaining: "விளக்குகிறது...",
    shortening: "சுருக்குகிறது...",
    translatedAnswer: "மொழிபெயர்ப்பு",
    errorPrefix: "பதிலைப் பெற முடியவில்லை.",
    tryAgain: "சிறிது நேரம் கழித்து மீண்டும் முயற்சி செய்.",
    tutorBusy: "ஆசிரியர் சேவை தற்காலிகமாகப் பிஸியாக உள்ளது. சிறிது நேரம் கழித்து மீண்டும் முயற்சி செய்.",
    parentTeacher: "பெற்றோர் மற்றும் ஆசிரியர் பலகையைத் திற.",
    regionNav: "முதன்மை வழிசெலுத்தல்",
    regionChat: "ஆசிரியருடனான உரையாடல்",
    status: "சேவை நிலை",
    selected: "தேர்ந்தெடுக்கப்பட்டது",
  },
};

const extendedCopy: Record<Locale, Record<string, string>> = {
  English: {
    family: "Family space",
    preview: "UI PREVIEW",
    practiceIntro: "A short, just-for-fun maths warm-up for your selected grade.",
    practiceKind: "QUICK MATHS",
    startPractice: "Start practice",
    solvePrompt: "Solve this:",
    chooseAnswer: "Choose your answer",
    correctAnswer: "That's right! Great thinking.",
    incorrectAnswer: "Good try! Let's look at the answer together.",
    nextQuestion: "Next question",
    finishPractice: "See my result",
    playAgain: "Play again",
    score: "Your score",
    question: "Question",
    of: "of",
    correctCount: "correct",
    practiceNote: "This is a simple practice preview, not a verified textbook activity. Your answers are kept only on this page and are not saved.",
    progressIntro: "A little progress is still progress. Here's what happened in this visit.",
    sessionOnly: "This is only for the current visit",
    questionsAnswered: "Questions answered",
    rightAnswers: "Right answers",
    learningActivity: "Practice activity",
    noActivity: "Complete a practice round to see your visit summary here.",
    badgesTitle: "Learning badges",
    badgesPending: "Badges will appear after secure accounts and progress tracking are connected.",
    familyTitle: "A learning space for families",
    familyIntro: "A clear view of a learner's journey, designed for parents and teachers.",
    parentRole: "Parent view",
    teacherRole: "Teacher view",
    parentRoleDescription: "Parents should only see learners securely linked to their own family account.",
    teacherRoleDescription: "Teachers should only see learners authorised for their classes or school role.",
    secureGateTitle: "Student information is protected",
    secureGateText: "A real dashboard must verify your sign-in and your relationship to each student before showing any personal learning records.",
    secureGateNote: "Secure sign-in and authorised student records are not connected yet. No student data is shown in this preview.",
    dashboardFeatureOne: "Learning overview",
    dashboardFeatureOneText: "Review verified activity and learning progress once a student account is connected.",
    dashboardFeatureTwo: "Subjects and practice",
    dashboardFeatureTwoText: "See the subjects and practice activities assigned to an authorised learner.",
    dashboardFeatureThree: "Support their learning",
    dashboardFeatureThreeText: "Notice what a learner has practised and where a kind explanation may help.",
    dashboardFeatureFour: "Privacy first",
    dashboardFeatureFourText: "Only linked parents or authorised teachers should be able to access a learner's records.",
    dashboardNoRecords: "No learner records are loaded. Sign-in and student linking are required before this dashboard can show data.",
  },
  Sinhala: {
    family: "පවුලේ ඉගෙනුම් පිටුව",
    preview: "පෙරදසුන",
    practiceIntro: "තෝරාගත් ශ්‍රේණිය සඳහා කෙටි ගණිත පුහුණුවක්.",
    practiceKind: "කෙටි ගණිත පුහුණුව",
    startPractice: "පුහුණුව අරඹන්න",
    solvePrompt: "ගණනය කරන්න:",
    chooseAnswer: "පිළිතුර තෝරන්න",
    correctAnswer: "හරි! හොඳින් සිතුවා.",
    incorrectAnswer: "හොඳ උත්සාහයක්! පිළිතුර එකට බලමු.",
    nextQuestion: "ඊළඟ ප්‍රශ්නය",
    finishPractice: "ප්‍රතිඵලය බලන්න",
    playAgain: "නැවත කරන්න",
    score: "ඔබේ ලකුණු",
    question: "ප්‍රශ්නය",
    of: "න්",
    correctCount: "නිවැරදියි",
    practiceNote: "මෙය සරල පුහුණු පෙරදසුනක් පමණි; තහවුරු කළ පෙළපොත් ක්‍රියාකාරකමක් නොවේ. පිළිතුරු මෙම පිටුවේ පමණක් තාවකාලිකව පවතින අතර සුරැකෙන්නේ නැත.",
    progressIntro: "කුඩා ප්‍රගතියත් වටිනවා. මේ පිවිසුමේ සිදු වූ දේ මෙන්න.",
    sessionOnly: "මෙය මෙම පිවිසුමට පමණි",
    questionsAnswered: "පිළිතුරු දුන් ප්‍රශ්න",
    rightAnswers: "නිවැරදි පිළිතුරු",
    learningActivity: "පුහුණු ක්‍රියාකාරකම",
    noActivity: "මෙහි පිවිසුම් සාරාංශය බැලීමට පුහුණු වටයක් සම්පූර්ණ කරන්න.",
    badgesTitle: "ඉගෙනුම් ලාංඡන",
    badgesPending: "ආරක්ෂිත ගිණුම් සහ ප්‍රගති සටහන් සම්බන්ධ කළ පසු ලාංඡන පෙන්වනු ඇත.",
    familyTitle: "පවුල් සඳහා ඉගෙනුම් අවකාශය",
    familyIntro: "දෙමාපියන්ට සහ ගුරුවරුන්ට ඉගෙනුම් ගමන පැහැදිලිව බැලීමට සැලසුම් කර ඇත.",
    parentRole: "දෙමාපිය දසුන",
    teacherRole: "ගුරු දසුන",
    parentRoleDescription: "දෙමාපියන්ට තම පවුල් ගිණුමට ආරක්ෂිතව සම්බන්ධ කළ ශිෂ්‍යයන් පමණක් පෙන්විය යුතුය.",
    teacherRoleDescription: "ගුරුවරුන්ට තම පන්තියට හෝ පාසල් භූමිකාවට අවසර ඇති ශිෂ්‍යයන් පමණක් පෙන්විය යුතුය.",
    secureGateTitle: "ශිෂ්‍ය තොරතුරු ආරක්ෂිතයි",
    secureGateText: "පුද්ගලික ඉගෙනුම් වාර්තා පෙන්වීමට පෙර, සැබෑ පුවරුවක් ඔබේ පිවිසුමත් ශිෂ්‍යයා සමඟ ඇති සම්බන්ධතාවත් තහවුරු කළ යුතුය.",
    secureGateNote: "ආරක්ෂිත පිවිසුම සහ අවසර ලත් ශිෂ්‍ය වාර්තා තවම සම්බන්ධ කර නැහැ. මෙම පෙරදසුනේ ශිෂ්‍ය දත්ත පෙන්වන්නේ නැහැ.",
    dashboardFeatureOne: "ඉගෙනුම් සාරාංශය",
    dashboardFeatureOneText: "ශිෂ්‍ය ගිණුමක් සම්බන්ධ කළ පසු තහවුරු කළ ක්‍රියාකාරකම් සහ ප්‍රගතිය බලන්න.",
    dashboardFeatureTwo: "විෂයයන් සහ පුහුණුව",
    dashboardFeatureTwoText: "අවසර ලත් ශිෂ්‍යයෙකුට නියම කළ විෂයයන් සහ පුහුණු ක්‍රියාකාරකම් බලන්න.",
    dashboardFeatureThree: "ඉගෙනීමට සහාය වන්න",
    dashboardFeatureThreeText: "ශිෂ්‍යයා පුහුණු වූ දේ සහ තවත් සරල පැහැදිලි කිරීමක් අවශ්‍ය තැන් හඳුනාගන්න.",
    dashboardFeatureFour: "පෞද්ගලිකත්වය ප්‍රමුඛයි",
    dashboardFeatureFourText: "සම්බන්ධිත දෙමාපියන්ට හෝ අවසර ලත් ගුරුවරුන්ට පමණක් ශිෂ්‍ය වාර්තා බැලිය හැකිය.",
    dashboardNoRecords: "ශිෂ්‍ය වාර්තා පූරණය කර නැහැ. දත්ත පෙන්වීමට පිවිසුම සහ ශිෂ්‍ය සම්බන්ධ කිරීම අවශ්‍යයි.",
  },
  Tamil: {
    family: "குடும்பப் பகுதி",
    preview: "முன்னோட்டம்",
    practiceIntro: "தேர்ந்தெடுத்த வகுப்புக்கான சிறிய கணிதப் பயிற்சி.",
    practiceKind: "சிறிய கணிதப் பயிற்சி",
    startPractice: "பயிற்சியைத் தொடங்கு",
    solvePrompt: "கணக்கிடு:",
    chooseAnswer: "உன் பதிலைத் தேர்ந்தெடு",
    correctAnswer: "சரியான பதில்! நன்றாகச் சிந்தித்தாய்.",
    incorrectAnswer: "நல்ல முயற்சி! சரியான பதிலை ஒன்றாகப் பார்ப்போம்.",
    nextQuestion: "அடுத்த கேள்வி",
    finishPractice: "முடிவைப் பார்",
    playAgain: "மீண்டும் விளையாடு",
    score: "உன் மதிப்பெண்",
    question: "கேள்வி",
    of: "இல்",
    correctCount: "சரி",
    practiceNote: "இது ஒரு எளிய பயிற்சி முன்னோட்டம்; சரிபார்க்கப்பட்ட பாடநூல் செயல்பாடு அல்ல. உன் பதில்கள் இந்தப் பக்கத்தில் மட்டும் தற்காலிகமாக இருக்கும்; சேமிக்கப்படாது.",
    progressIntro: "சிறிய முன்னேற்றமும் முக்கியம். இந்த வருகையில் நடந்தவை இங்கே.",
    sessionOnly: "இது தற்போதைய வருகைக்கு மட்டுமே",
    questionsAnswered: "பதிலளித்த கேள்விகள்",
    rightAnswers: "சரியான பதில்கள்",
    learningActivity: "பயிற்சி",
    noActivity: "இந்த வருகையின் சுருக்கத்தைப் பார்க்க ஒரு பயிற்சியை முடி.",
    badgesTitle: "கற்றல் பதக்கங்கள்",
    badgesPending: "பாதுகாப்பான கணக்குகளும் முன்னேற்றப் பதிவுகளும் இணைக்கப்பட்ட பிறகு பதக்கங்கள் தோன்றும்.",
    familyTitle: "குடும்பங்களுக்கான கற்றல் பகுதி",
    familyIntro: "பெற்றோரும் ஆசிரியரும் மாணவரின் கற்றல் பயணத்தைப் பார்க்க வடிவமைக்கப்பட்டது.",
    parentRole: "பெற்றோர் பார்வை",
    teacherRole: "ஆசிரியர் பார்வை",
    parentRoleDescription: "பெற்றோர் தங்கள் குடும்பக் கணக்குடன் பாதுகாப்பாக இணைக்கப்பட்ட மாணவர்களை மட்டுமே பார்க்க வேண்டும்.",
    teacherRoleDescription: "ஆசிரியர்கள் தங்கள் வகுப்பு அல்லது பள்ளிப் பொறுப்புக்கு அனுமதிக்கப்பட்ட மாணவர்களை மட்டுமே பார்க்க வேண்டும்.",
    secureGateTitle: "மாணவர் தகவல் பாதுகாக்கப்படுகிறது",
    secureGateText: "தனிப்பட்ட கற்றல் பதிவுகளைக் காட்டுவதற்கு முன், உண்மையான பலகை உன் உள்நுழைவையும் மாணவருடனான தொடர்பையும் சரிபார்க்க வேண்டும்.",
    secureGateNote: "பாதுகாப்பான உள்நுழைவும் அனுமதிக்கப்பட்ட மாணவர் பதிவுகளும் இன்னும் இணைக்கப்படவில்லை. இந்த முன்னோட்டத்தில் மாணவர் தரவு காட்டப்படாது.",
    dashboardFeatureOne: "கற்றல் சுருக்கம்",
    dashboardFeatureOneText: "மாணவர் கணக்கு இணைக்கப்பட்டதும் சரிபார்க்கப்பட்ட செயல்பாடுகளையும் முன்னேற்றத்தையும் பார்.",
    dashboardFeatureTwo: "பாடங்களும் பயிற்சியும்",
    dashboardFeatureTwoText: "அனுமதிக்கப்பட்ட மாணவருக்கான பாடங்களையும் பயிற்சிகளையும் பார்.",
    dashboardFeatureThree: "கற்றலுக்கு உதவு",
    dashboardFeatureThreeText: "மாணவர் பயிற்சி செய்தவற்றையும் எளிய விளக்கம் தேவைப்படும் இடங்களையும் அறிந்துகொள்.",
    dashboardFeatureFour: "தனியுரிமையே முதன்மை",
    dashboardFeatureFourText: "இணைக்கப்பட்ட பெற்றோர் அல்லது அனுமதிக்கப்பட்ட ஆசிரியர் மட்டுமே மாணவர் பதிவுகளை அணுக வேண்டும்.",
    dashboardNoRecords: "மாணவர் பதிவுகள் ஏற்றப்படவில்லை. தரவைக் காட்ட உள்நுழைவும் மாணவர் இணைப்பும் தேவை.",
  },
};

function mediumName(medium: Locale): string {
  return medium === "Sinhala" ? "සිංහල" : medium === "Tamil" ? "தமிழ்" : "English";
}

function App() {
  const [theme, setTheme] = useState<"light" | "dark">(
    () => window.localStorage.getItem("sl-scholar-ai-theme") === "dark" ? "dark" : "light",
  );
  const [locale, setLocale] = useState<Locale>("English");
  const [bookMedium, setBookMedium] = useState<Locale>("English");
  const [grade, setGrade] = useState(1);
  const [subject, setSubject] = useState(subjectsFor(1, "English")[0]);
  const [page, setPage] = useState<Page>("home");
  const [apiStatus, setApiStatus] = useState<ApiStatus>("checking");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [transformingMessageId, setTransformingMessageId] = useState<number | null>(null);
  const [transformingAction, setTransformingAction] = useState<AnswerAction | null>(null);
  const [transformationErrors, setTransformationErrors] = useState<Record<number, string>>({});
  const [error, setError] = useState("");
  const [retryQuestion, setRetryQuestion] = useState("");
  const [authToken, setAuthToken] = useState<string | null>(null);
  const [familyUser, setFamilyUser] = useState<FamilyUser | null>(null);
  const [selectedStudent, setSelectedStudent] = useState<Student | null>(null);
  const [progressRefresh, setProgressRefresh] = useState(0);
  const nextMessageId = useRef(1);
  const questionInput = useRef<HTMLTextAreaElement>(null);
  const t = copy[locale];
  const extra = extendedCopy[locale];
  const availableSubjects = useMemo(
    () => subjectsFor(grade, bookMedium),
    [grade, bookMedium],
  );
  const effectiveBookMedium = useMemo(
    () => textbookMediumForSubject(grade, subject, bookMedium),
    [grade, subject, bookMedium],
  );

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    window.localStorage.setItem("sl-scholar-ai-theme", theme);
  }, [theme]);

  useEffect(() => {
    if (!availableSubjects.includes(subject)) {
      setSubject(availableSubjects[0] ?? "");
    }
  }, [availableSubjects, subject]);

  useEffect(() => {
    const controller = new AbortController();
    fetch(`${getApiBaseUrl()}/health`, { signal: controller.signal })
      .then((response) => {
        if (!response.ok) {
          throw new Error("Health check failed.");
        }
        setApiStatus("online");
      })
      .catch((fetchError: unknown) => {
        if (fetchError instanceof DOMException && fetchError.name === "AbortError") {
          return;
        }
        setApiStatus("offline");
      });
    return () => controller.abort();
  }, []);

  async function askTutor(text: string) {
    const trimmed = text.trim();
    if (!trimmed || busy || !subject) {
      return;
    }

    setMessages((current) => [
      ...current,
      { id: nextMessageId.current++, role: "student", text: trimmed },
    ]);
    setQuestion("");
    setBusy(true);
    setError("");
    setRetryQuestion("");
    setPage("tutor");

    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 90_000);
    try {
      const response = await fetch(`${getApiBaseUrl()}/learning/ask`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        signal: controller.signal,
        body: JSON.stringify({
          question: trimmed,
          grade,
          subject,
          medium: effectiveBookMedium,
          answer_language: locale,
          conversation_history: messages
            .filter((message) => !(message.role === "student" && message.text === trimmed))
            .slice(-8)
            .map(({ role, text }) => ({ role, text })),
        }),
      });
      const payload: unknown = await response.json().catch(() => null);
      if (!response.ok) {
        const detailValue =
          typeof payload === "object" && payload !== null && "detail" in payload
            ? payload.detail
            : null;
        if (
          response.status === 503 &&
          typeof detailValue === "object" &&
          detailValue !== null &&
          "code" in detailValue &&
          detailValue.code === "tutor_temporarily_busy"
        ) {
          throw new Error(t.tutorBusy);
        }
        const detail =
          typeof detailValue === "string"
            ? detailValue
            : `${t.errorPrefix} ${t.tryAgain}`;
        throw new Error(detail);
      }
      if (!isLearningAnswer(payload)) {
        throw new Error(`${t.errorPrefix} ${t.tryAgain}`);
      }
      setMessages((current) => [
        ...current,
        {
          id: nextMessageId.current++,
          role: "tutor",
          text: payload.answer,
          status: payload.status,
          sources: payload.sources,
          question: trimmed,
          grade,
          subject,
          medium: effectiveBookMedium,
          answerLanguage: locale,
        },
      ]);
    } catch (requestError: unknown) {
      const message =
        requestError instanceof DOMException && requestError.name === "AbortError"
          ? t.tryAgain
          : requestError instanceof Error
            ? requestError.message
            : t.tryAgain;
      setError(message);
      setRetryQuestion(trimmed);
    } finally {
      window.clearTimeout(timeout);
      setBusy(false);
    }
  }

  function handleQuestionSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void askTutor(question);
  }

  async function transformAnswer(
    message: ChatMessage,
    action: AnswerAction,
    targetLanguage?: Locale,
  ) {
    if (
      transformingMessageId !== null ||
      !message.question ||
      message.grade === undefined ||
      !message.subject ||
      !message.medium ||
      !message.answerLanguage
    ) {
      return;
    }
    setTransformingMessageId(message.id);
    setTransformingAction(action);
    setTransformationErrors((current) => ({ ...current, [message.id]: "" }));
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 90_000);
    try {
      const response = await fetch(`${getApiBaseUrl()}/learning/transform-answer`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        signal: controller.signal,
        body: JSON.stringify({
          answer: message.text,
          question: message.question,
          grade: message.grade,
          subject: message.subject,
          medium: message.medium,
          answer_language: message.answerLanguage,
          action,
          ...(targetLanguage ? { target_language: targetLanguage } : {}),
        }),
      });
      const payload: unknown = await response.json().catch(() => null);
      if (!response.ok) {
        const detail =
          typeof payload === "object" && payload !== null && "detail" in payload
            ? payload.detail
            : null;
        if (
          response.status === 503 &&
          typeof detail === "object" &&
          detail !== null &&
          "code" in detail &&
          detail.code === "tutor_temporarily_busy"
        ) {
          throw new Error(t.tutorBusy);
        }
        if (typeof detail === "string" && detail.trim()) {
          throw new Error(detail);
        }
        throw new Error(`${t.transformationFailed} (${response.status})`);
      }
      if (
        typeof payload !== "object" ||
        payload === null ||
        !("answer" in payload) ||
        typeof payload.answer !== "string" ||
        !payload.answer.trim()
      ) {
        throw new Error(t.transformationFailed);
      }
      const transformedText = payload.answer.trim();
      const language = action === "translate"
        ? targetLanguage ?? message.answerLanguage
        : message.answerLanguage;
      setMessages((current) =>
        current.map((item) => item.id !== message.id
          ? item
          : {
              ...item,
              transformations: [
                ...(item.transformations ?? []).filter(
                  (transformation) =>
                    transformation.action !== action ||
                    transformation.language !== language,
                ),
                { action, language, text: transformedText },
              ],
            }),
      );
    } catch (requestError: unknown) {
      setTransformationErrors((current) => ({
        ...current,
        [message.id]:
          requestError instanceof DOMException && requestError.name === "AbortError"
            ? t.tryAgain
            : requestError instanceof Error
              ? requestError.message
              : t.transformationFailed,
      }));
    } finally {
      window.clearTimeout(timeout);
      setTransformingMessageId(null);
      setTransformingAction(null);
    }
  }

  function handleQuestionKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      event.currentTarget.form?.requestSubmit();
    }
  }

  function startNewChat() {
    if (messages.length && !window.confirm(t.clearConfirm)) {
      return;
    }
    setMessages([]);
    setError("");
    setRetryQuestion("");
    setQuestion("");
  }

  function openTutor() {
    setPage("tutor");
    window.requestAnimationFrame(() => questionInput.current?.focus());
  }

  const handleSession = useCallback(
    (token: string | null, user: FamilyUser | null) => {
      setAuthToken(token);
      setFamilyUser(user);
      if (!token) setSelectedStudent(null);
    },
    [],
  );
  const handleStudentSelected = useCallback((student: Student | null) => {
    setSelectedStudent(student);
    if (student) setGrade(student.grade);
  }, []);
  const latestTutorText =
    [...messages].reverse().find((message) => message.role === "tutor")?.text ?? "";

  const statusLabel = {
    checking: t.apiChecking,
    online: t.apiOnline,
    offline: t.apiOffline,
  }[apiStatus];

  return (
    <div className="app-shell">
      <aside className="sidebar" aria-label={t.regionNav}>
        <a className="brand" href="#home" onClick={() => setPage("home")}>
          <img className="brand-logo" src="/sl-scholar-ai-logo.png" alt={t.brand} />
        </a>

        <nav className="main-nav" aria-label={t.regionNav}>
          <button className={page === "home" ? "nav-item active" : "nav-item"} onClick={() => setPage("home")}>
            <span aria-hidden="true">⌂</span>{t.home}
          </button>
          <button className={page === "tutor" ? "nav-item active" : "nav-item"} onClick={openTutor}>
            <span aria-hidden="true">✎</span>{t.tutor}
          </button>
          <button className={page === "practice" ? "nav-item active" : "nav-item"} onClick={() => setPage("practice")}>
            <span aria-hidden="true">✿</span>{t.practice}
          </button>
          <button className={page === "coloring" ? "nav-item active" : "nav-item"} onClick={() => setPage("coloring")}>
            <span aria-hidden="true">🎨</span>{t.coloringNav}
          </button>
          <button className={page === "progress" ? "nav-item active" : "nav-item"} onClick={() => setPage("progress")}>
            <span aria-hidden="true">◷</span>{t.progress}
          </button>
          <button className={page === "family" ? "nav-item active" : "nav-item"} onClick={() => setPage("family")}>
            <span aria-hidden="true">♡</span>{extra.family}
          </button>
        </nav>

        <div className="sidebar-note">
          <span className={`status-dot status-dot--${apiStatus}`} aria-hidden="true" />
          <span>
            <strong>{t.status}</strong>
            <small role="status">{statusLabel}</small>
          </span>
        </div>

        <p className="sidebar-footer">{t.sidebarFooter}</p>
      </aside>

      <main className="main-area">
        <header className="topbar">
          <div className="mobile-brand">
            <img className="mobile-brand-logo" src="/sl-scholar-ai-logo.png" alt={t.brand} />
          </div>
          <div className="topbar-spacer" />
          <label className="language-control">
            <span className="sr-only">Interface language</span>
            <span aria-hidden="true">文</span>
            <select value={locale} onChange={(event) => setLocale(event.target.value as Locale)}>
              <option value="English">English</option>
              <option value="Sinhala">සිංහල</option>
              <option value="Tamil">தமிழ்</option>
            </select>
          </label>
          <button
            className="theme-toggle"
            type="button"
            onClick={() => setTheme((current) => current === "light" ? "dark" : "light")}
            aria-label={theme === "light" ? t.switchToDarkMode : t.switchToLightMode}
            aria-pressed={theme === "dark"}
            title={theme === "light" ? t.switchToDarkMode : t.switchToLightMode}
          >
            <span aria-hidden="true">{theme === "light" ? "☾" : "☀"}</span>
          </button>
          <div className="student-avatar" aria-label="Student profile">🌱</div>
        </header>

        {page === "home" && (
          <section className="content home-content" aria-labelledby="welcome-title">
            <div className="welcome-banner">
              <div className="welcome-copy">
                <p className="eyebrow">{t.regionGrade}</p>
                <h1 id="welcome-title">{t.welcome}</h1>
                <p>{t.welcomeText}</p>
              </div>
              <div className="welcome-art" aria-hidden="true">
                <span className="sun">☀</span>
                <span className="book-art">📚</span>
                <span className="sparkle sparkle-one">✦</span>
                <span className="sparkle sparkle-two">✧</span>
              </div>
            </div>

            <div className="section-heading">
              <div>
                <p className="eyebrow">{t.exploreEyebrow}</p>
                <h2>{t.subjects}</h2>
                <p className="muted">{t.subjectHelp}</p>
              </div>
              <div className="grade-picker">
                <label htmlFor="grade-select">{t.grade}</label>
                <select id="grade-select" value={grade} onChange={(event) => setGrade(Number(event.target.value))}>
                  {[1, 2, 3, 4, 5].map((value) => (
                    <option key={value} value={value}>{t.gradeOption} {value}</option>
                  ))}
                </select>
              </div>
            </div>

            <div className="filter-row">
              <label htmlFor="book-language">{t.textbookLanguage}</label>
              <select id="book-language" value={bookMedium} onChange={(event) => setBookMedium(event.target.value as Locale)}>
                <option value="English">English</option>
                <option value="Sinhala">සිංහල</option>
                <option value="Tamil">தமிழ்</option>
              </select>
              <span className="filter-divider" aria-hidden="true" />
              <label htmlFor="answer-language">{t.answerLanguage}</label>
              <select id="answer-language" value={locale} onChange={(event) => setLocale(event.target.value as Locale)}>
                <option value="English">English</option>
                <option value="Sinhala">සිංහල</option>
                <option value="Tamil">தமிழ்</option>
              </select>
            </div>
            {bookMedium === "English" && (
              <p className="subject-source-note">{t.sourceLanguageNote}</p>
            )}

            {availableSubjects.length ? (
              <div
                className={`subject-grid${availableSubjects.length === 1 ? " subject-grid--single" : ""}`}
                aria-label={t.subjects}
              >
                {availableSubjects.map((item, index) => (
                  <button
                    className={`subject-card${subject === item ? " subject-card--selected" : ""}`}
                    key={item}
                    onClick={() => {
                      setSubject(item);
                      openTutor();
                    }}
                  >
                    <span className={`subject-icon subject-icon--${index % 4}`} aria-hidden="true">
                      {["✎", "◉", "❋", "⌘"][index % 4]}
                    </span>
                    <span className="subject-card-copy">
                      <span className="subject-name">{item}</span>
                      {bookMedium === "English" && (
                        <small className="subject-source-language">
                          {mediumName(textbookMediumForSubject(grade, item, bookMedium))}
                        </small>
                      )}
                    </span>
                    <span className="subject-arrow" aria-hidden="true">→</span>
                  </button>
                ))}
              </div>
            ) : (
              <p className="empty-state">{t.noSubjects}</p>
            )}

            <div className="home-lower-grid">
              <button className="tutor-promo" onClick={openTutor}>
                <span className="promo-icon" aria-hidden="true">💬</span>
                <span>
                  <strong>{t.ask}</strong>
                  <small>{t.tutorHelp}</small>
                </span>
                <span className="subject-arrow" aria-hidden="true">→</span>
              </button>
              <div className="honesty-card">
                <span className="honesty-icon" aria-hidden="true">📖</span>
                <div>
                  <strong>{t.emptyTitle}</strong>
                  <p>{t.emptyText}</p>
                </div>
              </div>
            </div>

            <button className="dashboard-limitation dashboard-link" onClick={() => setPage("family")}>
              {t.parentTeacher} <span aria-hidden="true">→</span>
            </button>
          </section>
        )}

        {page === "tutor" && (
          <section className="content tutor-content" aria-labelledby="tutor-title">
            <div className="tutor-heading">
              <div>
                <p className="eyebrow">{t.tutorEyebrow}</p>
                <h1 id="tutor-title">{t.tutor}</h1>
                <p className="muted">{t.tutorHelp}</p>
              </div>
              <button className="secondary-button" onClick={startNewChat} disabled={transformingMessageId !== null}>＋ {t.clear}</button>
            </div>

            <div className="chat-context">
              <label>
                <span>{t.grade}</span>
                <select value={grade} onChange={(event) => setGrade(Number(event.target.value))}>
                  {[1, 2, 3, 4, 5].map((value) => <option key={value} value={value}>{t.gradeOption} {value}</option>)}
                </select>
              </label>
              <label>
                <span>{t.textbookLanguage}</span>
                <select value={bookMedium} onChange={(event) => setBookMedium(event.target.value as Locale)}>
                  <option value="English">English</option>
                  <option value="Sinhala">සිංහල</option>
                  <option value="Tamil">தமிழ்</option>
                </select>
              </label>
              <label>
                <span>{t.subjects}</span>
                <select value={subject} onChange={(event) => setSubject(event.target.value)}>
                  {availableSubjects.map((item) => <option key={item} value={item}>{item}</option>)}
                </select>
              </label>
            </div>
            {bookMedium === "English" && (
              <p className="subject-source-note">{t.sourceLanguageNote}</p>
            )}

            <div className="chat-panel">
              <div className="chat-toolbar">
                <span><span className="tutor-avatar" aria-hidden="true">✦</span>{t.tutor}</span>
                <span className={`connection-pill connection-pill--${apiStatus}`}>
                  <span className="status-dot" aria-hidden="true" />{statusLabel}
                </span>
              </div>

              <div className="messages" aria-label={t.regionChat} aria-live="polite">
                {!messages.length && (
                  <div className="chat-empty">
                    <span className="chat-empty-icon" aria-hidden="true">📚</span>
                    <h2>{t.tutorWelcome}</h2>
                    <p>{t.tutorHelp}</p>
                  </div>
                )}
                {messages.map((message) => (
                  <article className={`message message--${message.role}`} key={message.id}>
                    <div className="message-avatar" aria-hidden="true">
                      {message.role === "student" ? "🌱" : "✦"}
                    </div>
                    <div className="message-body">
                      <p className="message-label">{message.role === "student" ? t.selected : t.brand}</p>
                      <p className="message-text">{message.text}</p>
                      {message.role === "tutor" && message.status === "grounded" && message.answerLanguage && (
                        <>
                          <div className="answer-actions" aria-label={t.answerActions}>
                            {[...(["English", "Sinhala", "Tamil"] as const)]
                              .filter((language) => language !== message.answerLanguage)
                              .map((language) => (
                                <button
                                  className="answer-action"
                                  key={language}
                                  type="button"
                                  disabled={transformingMessageId !== null}
                                  onClick={() => void transformAnswer(message, "translate", language)}
                                >
                                  {t.translateTo} {language}
                                </button>
                              ))}
                            <button
                              className="answer-action"
                              type="button"
                              disabled={transformingMessageId !== null}
                              onClick={() => void transformAnswer(message, "explain")}
                            >
                              {t.moreExplanation}
                            </button>
                            <button
                              className="answer-action"
                              type="button"
                              disabled={transformingMessageId !== null}
                              onClick={() => void transformAnswer(message, "short")}
                            >
                              {t.shortAnswer}
                            </button>
                          </div>
                          {transformingMessageId === message.id && (
                            <p className="answer-action-status" role="status">
                              {transformingAction === "translate"
                                ? t.translating
                                : transformingAction === "explain"
                                  ? t.explaining
                                  : t.shortening}
                            </p>
                          )}
                          {transformationErrors[message.id] && (
                            <p className="answer-action-error" role="alert">{transformationErrors[message.id]}</p>
                          )}
                          {!!message.transformations?.length && (
                            <div className="answer-transformations">
                              {message.transformations.map((transformation) => (
                                <section
                                  className="answer-transformation"
                                  key={`${transformation.action}:${transformation.language}`}
                                >
                                  <p className="answer-transformation-label">
                                    {transformation.action === "translate"
                                      ? `${t.translatedAnswer} ${transformation.language}`
                                      : transformation.action === "explain"
                                        ? t.moreExplanation
                                        : t.shortAnswer}
                                  </p>
                                  <p className="message-text">{transformation.text}</p>
                                </section>
                              ))}
                            </div>
                          )}
                        </>
                      )}
                      {message.role === "tutor" && message.status === "grounded" && (
                        <p className="grounded-label">✓ {t.verified}</p>
                      )}
                      {message.role === "tutor" && message.status === "general" && (
                        <p className="general-label">{t.generalAnswer}</p>
                      )}
                      {message.role === "tutor" && message.status === "abstained" && (
                        <p className="abstained-label">{t.abstained}</p>
                      )}
                      {!!message.sources?.length && (
                        <div className="source-list">
                          {message.sources.map((source) => (
                            <div className="source-card" key={source.chunk_id}>
                              <span className="source-icon" aria-hidden="true">📖</span>
                              <span>
                                <strong>{source.textbook_title ?? source.source_file.split(/[\\/]/).pop()}</strong>
                                <small>{t.page} {source.pdf_page_number}
                                  {source.chapter ? ` · ${t.chapter} ${source.chapter}` : ""}
                                  {source.lesson ? ` · ${t.lesson} ${source.lesson}` : ""}
                                </small>
                              </span>
                            </div>
                          ))}
                          <small className="source-note">{t.sourceNote}</small>
                        </div>
                      )}
                    </div>
                  </article>
                ))}
                {busy && (
                  <div className="loading-message" role="status">
                    <span className="loading-orb" aria-hidden="true">✦</span>
                    <span>{t.loading}</span>
                    <span className="loading-dots" aria-hidden="true">•••</span>
                  </div>
                )}
                {error && (
                  <div className="request-error" role="alert">
                    <span>{t.errorPrefix} {error}</span>
                    <button className="text-button" onClick={() => void askTutor(retryQuestion)} disabled={busy}>
                      {t.retry}
                    </button>
                  </div>
                )}
              </div>

              <form className="question-form" onSubmit={handleQuestionSubmit}>
                <VoiceControls
                  locale={locale}
                  latestTutorText={latestTutorText}
                  onTranscript={(transcript) =>
                    setQuestion((current) =>
                      `${current}${current.trim() ? " " : ""}${transcript}`,
                    )
                  }
                />
                <label className="sr-only" htmlFor="student-question">{t.question}</label>
                <textarea
                  id="student-question"
                  ref={questionInput}
                  value={question}
                  onChange={(event) => setQuestion(event.target.value)}
                  onKeyDown={handleQuestionKeyDown}
                  maxLength={1200}
                  rows={2}
                  placeholder={t.question}
                  disabled={busy}
                />
                <div className="composer-footer">
                  <span>{question.length}/1200 · {t.composerHint}</span>
                  <button type="submit" className="primary-button" disabled={busy || !question.trim() || !subject}>
                    {busy ? t.loading : t.send}<span aria-hidden="true">↑</span>
                  </button>
                </div>
              </form>
            </div>
          </section>
        )}

        {page === "coloring" && (
          <section className="content coloring-content" aria-label={t.coloringNav}>
            <ColoringActivity
              locale={locale}
              grade={grade}
              medium={effectiveBookMedium}
              subject={subject}
            />
          </section>
        )}

        {page === "practice" && (
          <TextbookQuiz
            locale={locale}
            token={authToken}
            student={selectedStudent}
            subject={subject}
            medium={bookMedium}
            onOpenFamily={() => setPage("family")}
            onProgressChanged={() => setProgressRefresh((current) => current + 1)}
          />
        )}

        {page === "progress" && (
          <FamilyDashboard
            locale={locale}
            user={familyUser}
            token={authToken}
            progressRefresh={progressRefresh}
            onSession={handleSession}
            onStudentSelected={handleStudentSelected}
          />
        )}

        {page === "family" && (
          <FamilyDashboard
            locale={locale}
            user={familyUser}
            token={authToken}
            progressRefresh={progressRefresh}
            onSession={handleSession}
            onStudentSelected={handleStudentSelected}
          />
        )}
      </main>
    </div>
  );
}

export default App;
