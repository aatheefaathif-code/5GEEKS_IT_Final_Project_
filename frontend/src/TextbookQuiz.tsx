import { useEffect, useState, type FormEvent } from "react";

import {
  apiRequest,
  type Locale,
  type SourceReference,
  type Student,
} from "./learningTypes";

type QuizQuestion = {
  question: string;
  options: string[];
  sources: SourceReference[];
};

type Quiz = {
  id: string;
  questions: QuizQuestion[];
};

type AnswerFeedback = {
  correct: boolean;
  correct_index: number;
  explanation: string;
  sources: SourceReference[];
};

type Result = {
  score: number;
  total: number;
  answers: AnswerFeedback[];
  new_badges: string[];
};

type QuizOptions = {
  subjects: string[];
  topics: string[];
};

type Props = {
  locale: Locale;
  token: string | null;
  student: Student | null;
  subject: string;
  medium: Locale;
  onOpenFamily: () => void;
  onProgressChanged: () => void;
};

const copy = {
  English: {
    eyebrow: "TEXTBOOK CHALLENGE",
    title: "Learn with a textbook quiz",
    help: "Choose a topic from your selected textbook. Questions are created only when verified pages are found.",
    textbookLanguage: "Textbook language",
    subject: "Subject",
    topic: "Topic or lesson name",
    topicPlaceholder: "Choose a textbook lesson or type a topic",
    topicsLoading: "Loading verified textbook lessons…",
    noTopics: "No verified lesson titles are listed yet. You can type a topic.",
    make: "Create my quiz",
    next: "Next question",
    finish: "Check my answers",
    again: "Try another topic",
    choose: "Choose one answer",
    question: "Question",
    of: "of",
    score: "Your score",
    correct: "That is right!",
    incorrect: "Good try. Let's learn from the textbook.",
    rightAnswer: "Textbook answer",
    source: "Textbook evidence",
    page: "PDF page",
    citationNotice: "References show only verified textbook pages used to make this question.",
    loginTitle: "Ask a parent or teacher to sign in",
    loginText: "Saved quizzes and progress are available only for an authorized student profile.",
    openFamily: "Open family dashboard",
    noEvidence: "We could not find enough verified textbook content for this topic. Try a different topic or ask your teacher.",
    badges: "New badges",
    loading: "Checking the textbook and building your quiz…",
    answerSaved: "Your quiz and result have been saved.",
    first_quiz: "First textbook quiz",
    careful_thinker: "Careful thinker",
    steady_learner: "Steady learner",
  },
  Sinhala: {
    eyebrow: "පෙළපොත් අභියෝගය",
    title: "පෙළපොත් ප්‍රශ්නාවලියකින් ඉගෙනගන්න",
    help: "තෝරාගත් පෙළපොතේ මාතෘකාවක් ලියන්න. තහවුරු කළ පිටු හමු වූ විට පමණක් ප්‍රශ්න සාදයි.",
    textbookLanguage: "පෙළපොත් භාෂාව",
    subject: "විෂය",
    topic: "මාතෘකාව හෝ පාඩමේ නම",
    topicPlaceholder: "තහවුරු කළ පාඩමක් තෝරන්න හෝ මාතෘකාවක් ලියන්න",
    topicsLoading: "තහවුරු කළ පාඩම් සොයමින්…",
    noTopics: "තහවුරු කළ පාඩම් මාතෘකා තවම ලැයිස්තුගත කර නැහැ. ඔබට මාතෘකාවක් ටයිප් කළ හැකිය.",
    make: "ප්‍රශ්නාවලිය සාදන්න",
    next: "ඊළඟ ප්‍රශ්නය",
    finish: "පිළිතුරු බලන්න",
    again: "වෙනත් මාතෘකාවක් උත්සාහ කරන්න",
    choose: "එක් පිළිතුරක් තෝරන්න",
    question: "ප්‍රශ්නය",
    of: "න්",
    score: "ඔබේ ලකුණු",
    correct: "ඒක හරි!",
    incorrect: "හොඳ උත්සාහයක්. පෙළපොතෙන් ඉගෙනගනිමු.",
    rightAnswer: "පෙළපොතේ පිළිතුර",
    source: "පෙළපොත් සාක්ෂිය",
    page: "PDF පිටුව",
    citationNotice: "මෙම ප්‍රශ්නය සැකසීමට භාවිත කළ තහවුරු කළ පෙළපොත් පිටු පමණක් පෙන්වයි.",
    loginTitle: "දෙමාපියෙකුගෙන් හෝ ගුරුවරයෙකුගෙන් පිවිසීමට කියන්න",
    loginText: "සුරැකි ප්‍රශ්නාවලි සහ ප්‍රගතිය ලබාගත හැක්කේ අවසර ලත් ශිෂ්‍ය පැතිකඩකට පමණි.",
    openFamily: "පවුල් පුවරුව විවෘත කරන්න",
    noEvidence: "මෙම මාතෘකාවට ප්‍රමාණවත් තහවුරු කළ පෙළපත් අන්තර්ගතයක් හමු වුණේ නැහැ. වෙනත් මාතෘකාවක් උත්සාහ කරන්න හෝ ගුරුවරයාගෙන් අසන්න.",
    badges: "අලුත් ලාංඡන",
    loading: "පෙළපොත පරීක්ෂා කර ප්‍රශ්නාවලිය සාදමින්…",
    answerSaved: "ඔබේ ප්‍රශ්නාවලිය සහ ප්‍රතිඵලය සුරැකුණා.",
    first_quiz: "පළමු පෙළපොත් ප්‍රශ්නාවලිය",
    careful_thinker: "සැලකිල්ලෙන් සිතන්නා",
    steady_learner: "අඛණ්ඩව ඉගෙනගන්නා",
  },
  Tamil: {
    eyebrow: "பாடநூல் சவால்",
    title: "பாடநூல் வினாடி வினாவில் கற்போம்",
    help: "தேர்ந்தெடுத்த பாடநூலிலிருந்து ஒரு தலைப்பை எழுதுங்கள். சரிபார்க்கப்பட்ட பக்கங்கள் கிடைத்தால் மட்டுமே கேள்விகள் உருவாகும்.",
    textbookLanguage: "பாடநூல் மொழி",
    subject: "பாடம்",
    topic: "தலைப்பு அல்லது பாடத்தின் பெயர்",
    topicPlaceholder: "சரிபார்க்கப்பட்ட பாடத்தைத் தேர்ந்தெடு அல்லது தலைப்பை எழுது",
    topicsLoading: "சரிபார்க்கப்பட்ட பாடங்களைத் தேடுகிறது…",
    noTopics: "சரிபார்க்கப்பட்ட பாடத் தலைப்புகள் இன்னும் பட்டியலிடப்படவில்லை. தலைப்பை எழுதலாம்.",
    make: "வினாடி வினாவை உருவாக்கு",
    next: "அடுத்த கேள்வி",
    finish: "என் பதில்களைச் சரிபார்",
    again: "வேறு தலைப்பை முயற்சி செய்",
    choose: "ஒரு பதிலைத் தேர்ந்தெடு",
    question: "கேள்வி",
    of: "இல்",
    score: "உன் மதிப்பெண்",
    correct: "சரியான பதில்!",
    incorrect: "நல்ல முயற்சி. பாடநூலிலிருந்து கற்போம்.",
    rightAnswer: "பாடநூல் பதில்",
    source: "பாடநூல் ஆதாரம்",
    page: "PDF பக்கம்",
    citationNotice: "இந்தக் கேள்வியை உருவாக்கப் பயன்படுத்திய சரிபார்க்கப்பட்ட பாடநூல் பக்கங்கள் மட்டுமே காட்டப்படும்.",
    loginTitle: "பெற்றோர் அல்லது ஆசிரியரிடம் உள்நுழையச் சொல்லுங்கள்",
    loginText: "சேமிக்கப்பட்ட வினாடி வினாக்களும் முன்னேற்றமும் அனுமதிக்கப்பட்ட மாணவர் சுயவிவரத்திற்கு மட்டுமே.",
    openFamily: "குடும்பப் பலகையைத் திற",
    noEvidence: "இந்தத் தலைப்புக்குப் போதுமான சரிபார்க்கப்பட்ட பாடநூல் உள்ளடக்கம் கிடைக்கவில்லை. வேறு தலைப்பை முயற்சி செய்யுங்கள் அல்லது ஆசிரியரிடம் கேளுங்கள்.",
    badges: "புதிய பதக்கங்கள்",
    loading: "பாடநூலைச் சரிபார்த்து வினாடி வினா உருவாக்கப்படுகிறது…",
    answerSaved: "உன் வினாடி வினாவும் முடிவும் சேமிக்கப்பட்டன.",
    first_quiz: "முதல் பாடநூல் வினாடி வினா",
    careful_thinker: "கவனமாகச் சிந்திப்பவர்",
    steady_learner: "தொடர்ந்து கற்பவர்",
  },
} satisfies Record<Locale, Record<string, string>>;

function isSource(value: unknown): value is SourceReference {
  return (
    typeof value === "object" &&
    value !== null &&
    "source_file" in value &&
    typeof value.source_file === "string" &&
    "pdf_page_number" in value &&
    typeof value.pdf_page_number === "number" &&
    "textbook_title" in value &&
    (typeof value.textbook_title === "string" || value.textbook_title === null) &&
    "chapter" in value &&
    (typeof value.chapter === "string" || value.chapter === null) &&
    "lesson" in value &&
    (typeof value.lesson === "string" || value.lesson === null)
  );
}

function isQuiz(value: unknown): value is Quiz {
  return (
    typeof value === "object" &&
    value !== null &&
    "id" in value &&
    typeof value.id === "string" &&
    "questions" in value &&
    Array.isArray(value.questions) &&
    value.questions.length >= 3 &&
    value.questions.every((question: unknown) => {
      if (typeof question !== "object" || question === null) return false;
      return (
        "question" in question &&
        typeof question.question === "string" &&
        "options" in question &&
        Array.isArray(question.options) &&
        question.options.every((option: unknown) => typeof option === "string") &&
        "sources" in question &&
        Array.isArray(question.sources) &&
        question.sources.length > 0 &&
        question.sources.every(isSource)
      );
    })
  );
}

function isQuizOptions(value: unknown): value is QuizOptions {
  return (
    typeof value === "object" &&
    value !== null &&
    "subjects" in value &&
    Array.isArray(value.subjects) &&
    value.subjects.every((item) => typeof item === "string") &&
    "topics" in value &&
    Array.isArray(value.topics) &&
    value.topics.every((item) => typeof item === "string")
  );
}

function isResult(value: unknown): value is Result {
  const isFeedback = (answer: unknown): answer is AnswerFeedback =>
    typeof answer === "object" &&
    answer !== null &&
    "correct" in answer &&
    typeof answer.correct === "boolean" &&
    "correct_index" in answer &&
    typeof answer.correct_index === "number" &&
    "explanation" in answer &&
    typeof answer.explanation === "string" &&
    "sources" in answer &&
    Array.isArray(answer.sources) &&
    answer.sources.every(isSource);
  return (
    typeof value === "object" &&
    value !== null &&
    "score" in value &&
    typeof value.score === "number" &&
    "total" in value &&
    typeof value.total === "number" &&
    "answers" in value &&
    Array.isArray(value.answers) &&
    value.answers.every(isFeedback) &&
    value.total === value.answers.length &&
    value.score <= value.total &&
    "new_badges" in value &&
    Array.isArray(value.new_badges) &&
    value.new_badges.every((badge: unknown) => typeof badge === "string")
  );
}

export function TextbookQuiz({
  locale,
  token,
  student,
  subject,
  medium,
  onOpenFamily,
  onProgressChanged,
}: Props) {
  const labels: Record<string, string> = copy[locale];
  const [topic, setTopic] = useState("");
  const [selectedMedium, setSelectedMedium] = useState(medium);
  const [selectedSubject, setSelectedSubject] = useState(subject);
  const [availableSubjects, setAvailableSubjects] = useState<string[]>(
    subject ? [subject] : [],
  );
  const [topicOptions, setTopicOptions] = useState<string[]>([]);
  const [loadingOptions, setLoadingOptions] = useState(false);
  const [optionsError, setOptionsError] = useState("");
  const [quiz, setQuiz] = useState<Quiz | null>(null);
  const [questionIndex, setQuestionIndex] = useState(0);
  const [selectedOption, setSelectedOption] = useState<number | null>(null);
  const [answers, setAnswers] = useState<number[]>([]);
  const [result, setResult] = useState<Result | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setSelectedMedium(medium);
  }, [medium]);

  useEffect(() => {
    if (!student || !token) {
      setTopicOptions([]);
      return;
    }
    const controller = new AbortController();
    const params = new URLSearchParams({ medium: selectedMedium });
    if (selectedSubject) params.set("subject", selectedSubject);
    setLoadingOptions(true);
    setOptionsError("");
    void apiRequest(
      `/family/students/${student.id}/quiz-options?${params.toString()}`,
      token,
      { signal: controller.signal },
    )
      .then((payload) => {
        if (!isQuizOptions(payload)) throw new Error(labels.noEvidence);
        setAvailableSubjects(payload.subjects);
        if (!payload.subjects.includes(selectedSubject) && payload.subjects[0]) {
          setSelectedSubject(payload.subjects[0]);
          setTopic("");
          return;
        }
        setTopicOptions(payload.topics);
      })
      .catch((requestError: unknown) => {
        if (controller.signal.aborted) return;
        setOptionsError(
          requestError instanceof Error ? requestError.message : labels.noEvidence,
        );
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoadingOptions(false);
      });
    return () => controller.abort();
  }, [labels.noEvidence, selectedMedium, selectedSubject, student?.id, token]);

  async function createQuiz(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!student || !token || !selectedSubject || !topic.trim()) return;
    setBusy(true);
    setError("");
    setResult(null);
    setQuiz(null);
    try {
      const payload = await apiRequest(
        `/family/students/${student.id}/quizzes`,
        token,
        {
          method: "POST",
          body: JSON.stringify({
            subject: selectedSubject,
            topic: topic.trim(),
            medium: selectedMedium,
            question_count: 5,
          }),
        },
      );
      if (!isQuiz(payload)) throw new Error(labels.noEvidence);
      setQuiz(payload);
      setQuestionIndex(0);
      setSelectedOption(null);
      setAnswers([]);
    } catch (requestError: unknown) {
      const message = requestError instanceof Error ? requestError.message : labels.noEvidence;
      setError(message.includes("not enough verified") ? labels.noEvidence : message);
    } finally {
      setBusy(false);
    }
  }

  async function submitAnswers(selectedAnswers: number[]) {
    if (!student || !token || !quiz) return;
    setBusy(true);
    setError("");
    try {
      const payload = await apiRequest(
        `/family/students/${student.id}/quizzes/${quiz.id}/submit`,
        token,
        {
          method: "POST",
          body: JSON.stringify({ answers: selectedAnswers }),
        },
      );
      if (!isResult(payload)) throw new Error("The quiz result could not be read.");
      setResult(payload);
      onProgressChanged();
    } catch (requestError: unknown) {
      setError(requestError instanceof Error ? requestError.message : "Could not save your result.");
    } finally {
      setBusy(false);
    }
  }

  function handleNext(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (selectedOption === null || !quiz) return;
    const updatedAnswers = [...answers, selectedOption];
    setAnswers(updatedAnswers);
    if (questionIndex === quiz.questions.length - 1) {
      void submitAnswers(updatedAnswers);
    } else {
      setQuestionIndex((index) => index + 1);
      setSelectedOption(null);
    }
  }

  const currentQuestion = quiz?.questions[questionIndex];
  const feedback = result?.answers[questionIndex];

  return (
    <section className="content feature-content" aria-labelledby="quiz-title">
      <div className="feature-heading">
        <div>
          <p className="eyebrow">{labels.eyebrow}</p>
          <h1 id="quiz-title">{labels.title}</h1>
          <p className="muted">{labels.help}</p>
        </div>
        <span className="practice-symbol" aria-hidden="true">📚</span>
      </div>
      {!token || !student ? (
        <div className="practice-intro-card">
          <div className="practice-illustration" aria-hidden="true">🔐</div>
          <div className="practice-intro-copy">
            <h2>{labels.loginTitle}</h2>
            <p>{labels.loginText}</p>
            <button className="primary-button" onClick={onOpenFamily}>{labels.openFamily}<span aria-hidden="true">→</span></button>
          </div>
        </div>
      ) : (
        <>
          {!quiz && (
            <form className="quiz-topic-form" onSubmit={(event) => void createQuiz(event)}>
              <p className="practice-chip">{student.display_name} · {locale === "Tamil" ? "வகுப்பு" : locale === "Sinhala" ? "ශ්‍රේණිය" : "Grade"} {student.grade}</p>
              <label htmlFor="quiz-medium">{labels.textbookLanguage}</label>
              <select
                id="quiz-medium"
                value={selectedMedium}
                onChange={(event) => {
                  setSelectedMedium(event.target.value as Locale);
                  setSelectedSubject("");
                  setAvailableSubjects([]);
                  setTopic("");
                  setTopicOptions([]);
                }}
                disabled={busy}
              >
                {(["English", "Sinhala", "Tamil"] as const).map((item) => (
                  <option key={item} value={item}>
                    {item === "Sinhala" ? "සිංහල" : item === "Tamil" ? "தமிழ்" : "English"}
                  </option>
                ))}
              </select>
              <label htmlFor="quiz-subject">{labels.subject}</label>
              <select
                id="quiz-subject"
                value={selectedSubject}
                onChange={(event) => {
                  setSelectedSubject(event.target.value);
                  setTopic("");
                  setTopicOptions([]);
                }}
                disabled={busy || loadingOptions || !availableSubjects.length}
                required
              >
                {availableSubjects.map((item) => (
                  <option key={item} value={item}>{item}</option>
                ))}
              </select>
              <label htmlFor="quiz-topic">{labels.topic}</label>
              <input
                id="quiz-topic"
                list="quiz-topic-options"
                value={topic}
                onChange={(event) => setTopic(event.target.value)}
                placeholder={labels.topicPlaceholder}
                required
                maxLength={240}
              />
              <datalist id="quiz-topic-options">
                {topicOptions.map((item) => <option key={item} value={item} />)}
              </datalist>
              {loadingOptions && <p className="muted" role="status">{labels.topicsLoading}</p>}
              {!loadingOptions && !topicOptions.length && (
                <p className="muted" role="status">{labels.noTopics}</p>
              )}
              {optionsError && <p className="request-error" role="alert">{optionsError}</p>}
              <button className="primary-button" disabled={busy || !selectedSubject || !topic.trim()}>{busy ? labels.loading : labels.make}<span aria-hidden="true">→</span></button>
            </form>
          )}
          {busy && !quiz && <p className="loading-message" role="status">{labels.loading}</p>}
          {quiz && currentQuestion && !result && (
            <form className="practice-card" onSubmit={handleNext}>
              <div className="practice-progress">
                <span>{labels.question} {questionIndex + 1} {labels.of} {quiz.questions.length}</span>
                <span>{student.display_name}</span>
              </div>
              <div className="practice-progress-track" aria-hidden="true">
                <span style={{ width: `${((questionIndex + 1) / quiz.questions.length) * 100}%` }} />
              </div>
              <div className="practice-question">
                <p>{currentQuestion.question}</p>
                <span className="muted">{labels.choose}</span>
              </div>
              <div className="answer-options">
                {currentQuestion.options.map((option, index) => (
                  <button
                    type="button"
                    className={selectedOption === index ? "answer-option answer-option--selected" : "answer-option"}
                    key={`${index}-${option}`}
                    onClick={() => setSelectedOption(index)}
                    aria-pressed={selectedOption === index}
                  >
                    {option}
                  </button>
                ))}
              </div>
              <div className="quiz-source-list">
                {currentQuestion.sources.map((source) => (
                  <small key={`${source.source_file}-${source.pdf_page_number}`}>
                    {labels.source}: {source.textbook_title ?? source.source_file.split(/[\\/]/).pop()} · {labels.page} {source.pdf_page_number}
                    {source.lesson ? ` · ${source.lesson}` : ""}
                  </small>
                ))}
                <small>{labels.citationNotice}</small>
              </div>
              <button className="primary-button" disabled={selectedOption === null || busy}>
                {questionIndex === quiz.questions.length - 1 ? labels.finish : labels.next}<span aria-hidden="true">→</span>
              </button>
            </form>
          )}
          {result && quiz && (
            <div className="practice-card practice-result">
              <p className="eyebrow">{labels.score}</p>
              <h2>{result.score} / {result.total}</h2>
              <p className="success-notice" role="status">{labels.answerSaved}</p>
              {result.new_badges.length > 0 && (
                <div className="earned-badges"><strong>{labels.badges}</strong>{result.new_badges.map((badge) => <span className="earned-badge" key={badge}>✦ {labels[badge] ?? badge}</span>)}</div>
              )}
              <div className="quiz-review">
                {quiz.questions.map((question, index) => {
                  const answer = result.answers[index];
                  return (
                    <article className="quiz-review-item" key={`${index}-${question.question}`}>
                      <h3>{index + 1}. {question.question}</h3>
                      <p>{answer.correct ? labels.correct : labels.incorrect}</p>
                      <p><strong>{labels.rightAnswer}:</strong> {question.options[answer.correct_index]}</p>
                      <p>{answer.explanation}</p>
                      <small>{answer.sources.map((source) => `${source.textbook_title ?? source.source_file.split(/[\\/]/).pop()} · ${labels.page} ${source.pdf_page_number}`).join(" · ")}</small>
                    </article>
                  );
                })}
              </div>
              <button className="primary-button" onClick={() => { setQuiz(null); setResult(null); setAnswers([]); setTopic(""); }}>{labels.again}</button>
            </div>
          )}
        </>
      )}
      {error && <p className="request-error" role="alert">{error}</p>}
    </section>
  );
}
