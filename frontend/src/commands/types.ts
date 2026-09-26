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
  cardSlots?: [string, string, string];
};

export type SwapCommand = {
  type: "swap";
  frontIndex: number;
  backIndex: number;
};

export type ScenarioCommand =
  SkillCommand | MasterSkillCommand | AttackCommand | SwapCommand;
