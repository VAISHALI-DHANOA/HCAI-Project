export const MBTI_DIMENSIONS = [
  {
    label: "Energy",
    options: ["E", "I"] as const,
    descriptions: [
      "Extraversion: energized by interaction",
      "Introversion: energized by reflection",
    ],
  },
  {
    label: "Information",
    options: ["S", "N"] as const,
    descriptions: [
      "Sensing: focuses on facts and details",
      "Intuition: focuses on patterns and possibilities",
    ],
  },
  {
    label: "Decisions",
    options: ["T", "F"] as const,
    descriptions: [
      "Thinking: decides by logic and consistency",
      "Feeling: decides by values and impact on people",
    ],
  },
  {
    label: "Structure",
    options: ["J", "P"] as const,
    descriptions: [
      "Judging: prefers planning and closure",
      "Perceiving: prefers flexibility and openness",
    ],
  },
];

export interface MBTIQuestion {
  question: string;
  dimension: number;
  choiceA: string;
  choiceB: string;
}

export const MBTI_QUESTIONS: MBTIQuestion[] = [
  {
    question: "In a group discussion, this agent would most likely...",
    dimension: 0,
    choiceA: "Speak up first and think out loud",
    choiceB: "Listen carefully before sharing a considered response",
  },
  {
    question: "After a long debate session, this agent recharges by...",
    dimension: 0,
    choiceA: "Continuing to discuss with others over coffee",
    choiceB: "Taking time alone to reflect on what was said",
  },
  {
    question: "When analyzing a proposal, this agent focuses on...",
    dimension: 1,
    choiceA: "Concrete data, evidence, and practical details",
    choiceB: "The big picture, underlying patterns, and future possibilities",
  },
  {
    question: "When explaining their position, this agent tends to use...",
    dimension: 1,
    choiceA: "Specific examples and real-world cases",
    choiceB: "Metaphors, analogies, and abstract frameworks",
  },
  {
    question: "When two colleagues disagree, this agent's first instinct is to...",
    dimension: 2,
    choiceA: "Analyze the logical merits of each argument",
    choiceB: "Consider how each person feels and find harmony",
  },
  {
    question: "This agent would rather be known as...",
    dimension: 2,
    choiceA: "Fair and analytically rigorous",
    choiceB: "Compassionate and emotionally intelligent",
  },
  {
    question: "When a project deadline approaches, this agent prefers to...",
    dimension: 3,
    choiceA: "Have everything planned and completed ahead of time",
    choiceB: "Stay open to last-minute changes and new information",
  },
  {
    question: "This agent's ideal meeting style is...",
    dimension: 3,
    choiceA: "Structured agenda with clear action items",
    choiceB: "Open-ended exploration of ideas wherever they lead",
  },
];

export function scoreQuestionnaire(answers: number[]): string {
  const scores: [number, number][] = [
    [0, 0],
    [0, 0],
    [0, 0],
    [0, 0],
  ];
  answers.forEach((choice, i) => {
    const dim = MBTI_QUESTIONS[i].dimension;
    scores[dim][choice]++;
  });
  return scores
    .map((s, i) =>
      s[0] >= s[1] ? MBTI_DIMENSIONS[i].options[0] : MBTI_DIMENSIONS[i].options[1]
    )
    .join("");
}

const MBTI_PERSONA_MAP: Record<string, string> = {
  E: "Outgoing and energized by group interactions.",
  I: "Reflective and thoughtful, prefers to listen deeply before contributing.",
  S: "Detail-oriented and grounded in facts and practical experience.",
  N: "Imaginative and big-picture thinker, drawn to patterns and possibilities.",
  T: "Analytical and logic-driven, prioritizes objectivity.",
  F: "Empathetic and values-driven, considers human impact.",
  J: "Organized and decisive, prefers structure and clear plans.",
  P: "Adaptable and open-ended, enjoys exploring options.",
};

export function mbtiToPersonaModifier(mbtiType: string): string {
  return mbtiType
    .split("")
    .map((letter) => MBTI_PERSONA_MAP[letter] || "")
    .filter(Boolean)
    .join(" ");
}

export function enrichPersonaWithMBTI(basePersona: string, mbtiType: string): string {
  if (!mbtiType) return basePersona;
  const modifier = mbtiToPersonaModifier(mbtiType);
  return `${basePersona} Personality type (${mbtiType}): ${modifier}`;
}
