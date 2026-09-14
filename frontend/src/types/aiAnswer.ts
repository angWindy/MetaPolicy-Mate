export type AIAnswerBlock =
  | {
      id: string;
      type: "heading";
      text: string;
    }
  | {
      id: string;
      type: "paragraph";
      text: string;
    }
  | {
      id: string;
      type: "list";
      items: string[];
    };

