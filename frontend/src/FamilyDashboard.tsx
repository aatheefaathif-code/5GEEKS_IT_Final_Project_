import { useEffect, useState, type FormEvent } from "react";

import { apiRequest, isStudent, type FamilyUser, type Locale, type Student } from "./learningTypes";

type Badge = { badge_code: string; awarded_at: string };
type Progress = {
  completed_quizzes: number;
  correct_answers: number;
  answered_questions: number;
  badges: Badge[];
};

function isProgress(value: unknown): value is Progress {
  return (
    typeof value === "object" &&
    value !== null &&
    "completed_quizzes" in value &&
    typeof value.completed_quizzes === "number" &&
    "correct_answers" in value &&
    typeof value.correct_answers === "number" &&
    "answered_questions" in value &&
    typeof value.answered_questions === "number" &&
    "badges" in value &&
    Array.isArray(value.badges) &&
    value.badges.every(
      (badge: unknown) =>
        typeof badge === "object" &&
        badge !== null &&
        "badge_code" in badge &&
        typeof badge.badge_code === "string" &&
        "awarded_at" in badge &&
        typeof badge.awarded_at === "string",
    )
  );
}

type Props = {
  locale: Locale;
  user: FamilyUser | null;
  token: string | null;
  progressRefresh: number;
  onSession: (token: string | null, user: FamilyUser | null) => void;
  onStudentSelected: (student: Student | null) => void;
};

const text = {
  English: {
    signIn: "Sign in",
    signUp: "Create parent account",
    email: "Email",
    password: "Password (at least 8 characters)",
    parent: "Parent",
    teacher: "Teacher",
    signOut: "Sign out",
    createChild: "Add a child profile",
    childName: "Child's first name or nickname",
    grade: "Grade",
    add: "Add student",
    students: "Authorized students",
    select: "Select student",
    noStudents: "No authorized student profiles are linked to this account.",
    progress: "Saved learning progress",
    quizzes: "Completed textbook quizzes",
    correct: "Correct answers",
    badges: "Earned badges",
    noProgress: "No quiz attempts have been saved yet.",
    noBadges: "No badges earned yet. Keep learning!",
    first_quiz: "First textbook quiz",
    careful_thinker: "Careful thinker · 80% or more",
    steady_learner: "Steady learner · 3 quizzes",
    error: "Could not complete the request.",
    loading: "Loading secure student records…",
    signupSent: "Account created. If email confirmation is enabled, confirm your address before signing in.",
    roleNote: "Teacher accounts and student access must be approved by an administrator and the student's parent.",
    security: "Your access token stays in this browser tab and is never stored in local storage.",
  },
  Sinhala: {
    signIn: "පිවිසෙන්න",
    signUp: "දෙමාපිය ගිණුමක් සාදන්න",
    email: "විද්‍යුත් තැපෑල",
    password: "මුරපදය (අවම අකුරු 8)",
    parent: "දෙමාපිය",
    teacher: "ගුරු",
    signOut: "ඉවත් වන්න",
    createChild: "දරුවාගේ පැතිකඩ එක් කරන්න",
    childName: "දරුවාගේ මුල් නම හෝ අන්වර්ථ නම",
    grade: "ශ්‍රේණිය",
    add: "ශිෂ්‍යයා එක් කරන්න",
    students: "අවසර ලත් ශිෂ්‍යයන්",
    select: "ශිෂ්‍යයා තෝරන්න",
    noStudents: "මෙම ගිණුමට සම්බන්ධ කළ අවසර ලත් ශිෂ්‍ය පැතිකඩක් නැහැ.",
    progress: "සුරැකි ඉගෙනුම් ප්‍රගතිය",
    quizzes: "සම්පූර්ණ කළ පෙළපොත් ප්‍රශ්නාවලි",
    correct: "නිවැරදි පිළිතුරු",
    badges: "ලැබූ ලාංඡන",
    noProgress: "තවම ප්‍රශ්නාවලි උත්සාහයක් සුරැකී නැහැ.",
    noBadges: "තවම ලාංඡන ලැබී නැහැ. දිගටම ඉගෙනගන්න!",
    first_quiz: "පළමු පෙළපොත් ප්‍රශ්නාවලිය",
    careful_thinker: "සිතාමතා ඉගෙනගන්නා · 80% හෝ වැඩි",
    steady_learner: "අඛණ්ඩව ඉගෙනගන්නා · ප්‍රශ්නාවලි 3",
    error: "ඉල්ලීම සම්පූර්ණ කළ නොහැකි විය.",
    loading: "ආරක්ෂිත ශිෂ්‍ය වාර්තා පූරණය වෙමින්…",
    signupSent: "ගිණුම සාදා ඇත. විද්‍යුත් තැපෑල තහවුරු කිරීම සක්‍රිය නම්, පිවිසීමට පෙර එය තහවුරු කරන්න.",
    roleNote: "ගුරු ගිණුම් සහ ශිෂ්‍ය ප්‍රවේශය පරිපාලකයා සහ ශිෂ්‍යයාගේ දෙමාපියා විසින් අනුමත කළ යුතුය.",
    security: "ඔබේ පිවිසුම් ටෝකනය මෙම බ්‍රවුසර ටැබයේ පමණක් පවතී; local storage හි සුරකින්නේ නැහැ.",
  },
  Tamil: {
    signIn: "உள்நுழை",
    signUp: "பெற்றோர் கணக்கை உருவாக்கு",
    email: "மின்னஞ்சல்",
    password: "கடவுச்சொல் (குறைந்தது 8 எழுத்துகள்)",
    parent: "பெற்றோர்",
    teacher: "ஆசிரியர்",
    signOut: "வெளியேறு",
    createChild: "குழந்தையின் சுயவிவரத்தைச் சேர்",
    childName: "குழந்தையின் முதல் பெயர் அல்லது செல்லப்பெயர்",
    grade: "வகுப்பு",
    add: "மாணவரைச் சேர்",
    students: "அனுமதிக்கப்பட்ட மாணவர்கள்",
    select: "மாணவரைத் தேர்ந்தெடு",
    noStudents: "இந்தக் கணக்குடன் இணைக்கப்பட்ட அனுமதிக்கப்பட்ட மாணவர் சுயவிவரம் இல்லை.",
    progress: "சேமிக்கப்பட்ட கற்றல் முன்னேற்றம்",
    quizzes: "முடித்த பாடநூல் வினாடி வினாக்கள்",
    correct: "சரியான பதில்கள்",
    badges: "பெற்ற பதக்கங்கள்",
    noProgress: "இதுவரை வினாடி வினா முயற்சி சேமிக்கப்படவில்லை.",
    noBadges: "இதுவரை பதக்கங்கள் இல்லை. தொடர்ந்து கற்போம்!",
    first_quiz: "முதல் பாடநூல் வினாடி வினா",
    careful_thinker: "கவனமாகச் சிந்திப்பவர் · 80% அல்லது அதிகம்",
    steady_learner: "தொடர்ந்து கற்பவர் · 3 வினாடி வினாக்கள்",
    error: "கோரிக்கையை நிறைவேற்ற முடியவில்லை.",
    loading: "பாதுகாப்பான மாணவர் பதிவுகள் ஏற்றப்படுகின்றன…",
    signupSent: "கணக்கு உருவாக்கப்பட்டது. மின்னஞ்சல் உறுதிப்படுத்தல் இயக்கப்பட்டிருந்தால், உள்நுழைவதற்கு முன் முகவரியை உறுதிப்படுத்தவும்.",
    roleNote: "ஆசிரியர் கணக்குகளும் மாணவர் அணுகலும் நிர்வாகியும் மாணவரின் பெற்றோரும் ஒப்புதல் அளிக்க வேண்டும்.",
    security: "உள்நுழைவு டோக்கன் இந்த உலாவித் தாவலில் மட்டுமே இருக்கும்; local storage-இல் சேமிக்கப்படாது.",
  },
} satisfies Record<Locale, Record<string, string>>;

function isUser(value: unknown): value is FamilyUser {
  return (
    typeof value === "object" &&
    value !== null &&
    "id" in value &&
    typeof value.id === "string" &&
    "email" in value &&
    typeof value.email === "string" &&
    "role" in value &&
    (value.role === "parent" || value.role === "teacher") &&
    "full_name" in value &&
    (typeof value.full_name === "string" || value.full_name === null)
  );
}

export function FamilyDashboard({
  locale,
  user,
  token,
  progressRefresh,
  onSession,
  onStudentSelected,
}: Props) {
  const labels: Record<string, string> = text[locale];
  const [roleChoice, setRoleChoice] = useState<"parent" | "teacher">("parent");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [childName, setChildName] = useState("");
  const [childGrade, setChildGrade] = useState(1);
  const [students, setStudents] = useState<Student[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [progress, setProgress] = useState<Progress | null>(null);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!token) {
      setStudents([]);
      setProgress(null);
      setSelectedId("");
      onStudentSelected(null);
      return;
    }
    let active = true;
    void apiRequest("/family/students", token)
      .then((payload) => {
        if (!Array.isArray(payload) || !payload.every(isStudent)) {
          throw new Error(labels.error);
        }
        if (!active) return;
        setStudents(payload);
        const next = payload.find((student) => student.id === selectedId) ?? payload[0] ?? null;
        setSelectedId(next?.id ?? "");
        onStudentSelected(next);
      })
      .catch((requestError: unknown) => {
        if (!active) return;
        setError(requestError instanceof Error ? requestError.message : labels.error);
      });
    return () => {
      active = false;
    };
  }, [token, progressRefresh, selectedId, onStudentSelected, labels.error]);

  useEffect(() => {
    if (!token || !selectedId) {
      setProgress(null);
      return;
    }
    let active = true;
    void apiRequest(`/family/students/${selectedId}/progress`, token)
      .then((payload) => {
        if (active && isProgress(payload)) setProgress(payload);
      })
      .catch((requestError: unknown) => {
        if (active) {
          setError(requestError instanceof Error ? requestError.message : labels.error);
        }
      });
    return () => {
      active = false;
    };
  }, [token, selectedId, progressRefresh]);

  async function submitAuth(event: FormEvent<HTMLFormElement>, signup: boolean) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setNotice("");
    try {
      if (signup) {
        await apiRequest("/auth/signup", null, {
          method: "POST",
          body: JSON.stringify({ email, password }),
        });
        setNotice(labels.signupSent);
      } else {
        const result = await apiRequest("/auth/login", null, {
          method: "POST",
          body: JSON.stringify({ email, password }),
        });
        if (
          typeof result !== "object" ||
          result === null ||
          !("access_token" in result) ||
          typeof result.access_token !== "string" ||
          !("user" in result) ||
          !isUser(result.user)
        ) {
          throw new Error(labels.error);
        }
        onSession(result.access_token, result.user);
        setPassword("");
      }
    } catch (requestError: unknown) {
      setError(requestError instanceof Error ? requestError.message : labels.error);
    } finally {
      setBusy(false);
    }
  }

  async function addStudent(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token) return;
    setBusy(true);
    setError("");
    try {
      const added = await apiRequest("/family/students", token, {
        method: "POST",
        body: JSON.stringify({ display_name: childName, grade: childGrade }),
      });
      if (!isStudent(added)) throw new Error(labels.error);
      setStudents((current) => [...current, added]);
      setSelectedId(added.id);
      onStudentSelected(added);
      setChildName("");
    } catch (requestError: unknown) {
      setError(requestError instanceof Error ? requestError.message : labels.error);
    } finally {
      setBusy(false);
    }
  }

  function selectStudent(student: Student) {
    setSelectedId(student.id);
    onStudentSelected(student);
  }

  return (
    <div className="family-dashboard">
      <div className="family-hero">
        <div>
          <p className="eyebrow">{locale === "Tamil" ? "பாதுகாப்பான குடும்பப் பகுதி" : locale === "Sinhala" ? "ආරක්ෂිත පවුල් ප්‍රදේශය" : "SECURE FAMILY SPACE"}</p>
          <h1>{locale === "Tamil" ? "குடும்பக் கற்றல் பலகை" : locale === "Sinhala" ? "පවුලේ ඉගෙනුම් පුවරුව" : "Family learning dashboard"}</h1>
          <p>{locale === "Tamil" ? "பெற்றோர் கணக்குடன் இணைக்கப்பட்ட மாணவர் பதிவுகள் மட்டுமே இங்கே காட்டப்படும்." : locale === "Sinhala" ? "දෙමාපිය ගිණුමට සම්බන්ධ කළ ශිෂ්‍ය වාර්තා පමණක් මෙහි පෙන්වයි." : "Only student records authorized for your account appear here."}</p>
        </div>
        <div className="family-hero-art" aria-hidden="true">🏡</div>
      </div>

      {!user ? (
        <div className="family-auth-layout">
          <form className="family-auth-card" onSubmit={(event) => void submitAuth(event, false)}>
            <h2>{labels.signIn}</h2>
            <label>{labels.email}<input type="email" autoComplete="email" required value={email} onChange={(event) => setEmail(event.target.value)} /></label>
            <label>{labels.password}<input type="password" autoComplete="current-password" minLength={8} required value={password} onChange={(event) => setPassword(event.target.value)} /></label>
            <button className="primary-button" disabled={busy}>{labels.signIn}</button>
          </form>
          <div className="family-auth-card">
            <div className="role-switch" role="group" aria-label={locale === "Tamil" ? "கணக்கு வகை" : locale === "Sinhala" ? "ගිණුම් වර්ගය" : "Account type"}>
              <button type="button" className={roleChoice === "parent" ? "role-option role-option--active" : "role-option"} onClick={() => setRoleChoice("parent")}>{labels.parent}</button>
              <button type="button" className={roleChoice === "teacher" ? "role-option role-option--active" : "role-option"} onClick={() => setRoleChoice("teacher")}>{labels.teacher}</button>
            </div>
            {roleChoice === "parent" ? (
              <form onSubmit={(event) => void submitAuth(event, true)}>
                <h2>{labels.signUp}</h2>
                <label>{labels.email}<input type="email" autoComplete="email" required value={email} onChange={(event) => setEmail(event.target.value)} /></label>
                <label>{labels.password}<input type="password" autoComplete="new-password" minLength={8} required value={password} onChange={(event) => setPassword(event.target.value)} /></label>
                <button className="secondary-button" disabled={busy}>{labels.signUp}</button>
              </form>
            ) : (
              <div className="role-description">{labels.roleNote}</div>
            )}
          </div>
        </div>
      ) : (
        <section className="family-auth-card" aria-labelledby="account-title">
          <div className="family-account-heading">
            <div>
              <h2 id="account-title">{user.email}</h2>
              <p className="muted">{user.role === "parent" ? labels.parent : labels.teacher} · {labels.security}</p>
            </div>
            <button className="secondary-button" onClick={() => onSession(null, null)}>{labels.signOut}</button>
          </div>
          {user.role === "parent" && (
            <form className="student-create-form" onSubmit={(event) => void addStudent(event)}>
              <h3>{labels.createChild}</h3>
              <label>{labels.childName}<input required maxLength={80} value={childName} onChange={(event) => setChildName(event.target.value)} /></label>
              <label>{labels.grade}<select value={childGrade} onChange={(event) => setChildGrade(Number(event.target.value))}>{[1, 2, 3, 4, 5].map((grade) => <option key={grade} value={grade}>{labels.grade} {grade}</option>)}</select></label>
              <button className="primary-button" disabled={busy || !childName.trim()}>{labels.add}</button>
            </form>
          )}
          <h3>{labels.students}</h3>
          {students.length ? (
            <div className="student-list">
              {students.map((student) => (
                <button
                  className={student.id === selectedId ? "student-option student-option--active" : "student-option"}
                  key={student.id}
                  onClick={() => selectStudent(student)}
                  aria-pressed={student.id === selectedId}
                >
                  <span aria-hidden="true">🧒</span><strong>{student.display_name}</strong><small>{labels.grade} {student.grade}</small>
                </button>
              ))}
            </div>
          ) : (
            <p className="muted" role="status">{labels.noStudents}</p>
          )}
          {selectedId && (
            <div className="persisted-progress">
              <h3>{labels.progress}</h3>
              {progress ? (
                <>
                  <div className="progress-stat-grid">
                    <article><strong>{progress.completed_quizzes}</strong><span>{labels.quizzes}</span></article>
                    <article><strong>{progress.correct_answers}/{progress.answered_questions}</strong><span>{labels.correct}</span></article>
                  </div>
                  <h4>{labels.badges}</h4>
                  {progress.badges.length ? (
                    <div className="earned-badges">{progress.badges.map((badge) => (
                      <span className="earned-badge" key={badge.badge_code}>✦ {labels[badge.badge_code] ?? badge.badge_code}</span>
                    ))}</div>
                  ) : <p className="muted">{labels.noBadges}</p>}
                </>
              ) : <p className="muted" role="status">{labels.loading}</p>}
            </div>
          )}
        </section>
      )}
      {notice && <p className="success-notice" role="status">{notice}</p>}
      {error && <p className="request-error" role="alert">{error || labels.error}</p>}
      <p className="truth-note">{labels.roleNote}</p>
    </div>
  );
}
