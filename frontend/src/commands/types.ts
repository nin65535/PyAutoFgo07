export type SkillCommand = {
  type: "skill";
  skillIndex: number;
  targetIndex?: number;
};

export type MasterSkillCommand = {
  type: "master_skill";
  skillIndex: number;
  targetIndex?: number;
};

export type AttackCommand = {
  type: "attack";
  noblePhantasmIndexes: number[];
};

export type AttackCardsCommand = {
  type: "attack_cards";
  cardSlots: [string, string, string];
  frontMembers?: [string, string, string];
};

export type SwapCommand = {
  type: "swap";
  frontIndex: number;
  backIndex: number;
};

export type ScenarioCommand =
  | SkillCommand
  | MasterSkillCommand
  | AttackCommand
  | AttackCardsCommand
  | SwapCommand;
