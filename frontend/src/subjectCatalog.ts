import type { Locale } from "./learningTypes";

const subjectsByGradeAndMedium: Record<number, Record<Locale, string[]>> = {
  1: {
    English: ["English Language"],
    Sinhala: [
      "Buddhism",
      "Catholicism",
      "Christianity",
      "Islam",
      "Mathematics",
      "Sinhala Language",
    ],
    Tamil: [
      "Catholicism",
      "Christianity",
      "Islam",
      "Mathematics",
      "Tamil Language",
    ],
  },
  2: {
    English: ["English Language"],
    Sinhala: [
      "Buddhism",
      "Catholicism",
      "Christianity",
      "Islam",
      "Mathematics",
      "Sinhala Language",
    ],
    Tamil: [
      "Catholicism",
      "Christianity",
      "Hinduism",
      "Islam",
      "Mathematics",
      "Tamil Language",
    ],
  },
  3: {
    English: ["English Language"],
    Sinhala: [
      "Buddhism",
      "Catholicism",
      "Christianity",
      "Islam",
      "Mathematics",
      "Sinhala Language",
    ],
    Tamil: [
      "Catholicism",
      "Christianity",
      "Hinduism",
      "Islam",
      "Mathematics",
      "Tamil Language",
    ],
  },
  4: {
    English: ["English Language"],
    Sinhala: [
      "Buddhism",
      "Catholicism",
      "Christianity",
      "Islam",
      "Mathematics",
      "Sinhala Language",
    ],
    Tamil: [
      "Catholicism",
      "Christianity",
      "Hinduism",
      "Islam",
      "Mathematics",
      "Tamil Language",
    ],
  },
  5: {
    English: ["English Language"],
    Sinhala: [
      "Buddhism",
      "Catholicism",
      "Christianity",
      "Islam",
      "Mathematics",
      "Sinhala Language",
    ],
    Tamil: [
      "Catholicism",
      "Christianity",
      "Hinduism",
      "Islam",
      "Mathematics",
      "Scholarship Examination (multi-subject)",
      "Tamil Language",
    ],
  },
};

export function subjectsFor(grade: number, medium: Locale): string[] {
  const subjects = subjectsByGradeAndMedium[grade];
  if (!subjects) return [];
  if (medium !== "English") return [...subjects[medium]];
  return [...new Set(Object.values(subjects).flat())];
}

export function textbookMediumForSubject(
  grade: number,
  subject: string,
  selectedMedium: Locale,
): Locale {
  const subjects = subjectsByGradeAndMedium[grade];
  if (!subjects) return selectedMedium;
  if (subjects[selectedMedium].includes(subject)) return selectedMedium;
  if (selectedMedium !== "English") return selectedMedium;
  if (subjects.Tamil.includes(subject)) return "Tamil";
  if (subjects.Sinhala.includes(subject)) return "Sinhala";
  return "English";
}
