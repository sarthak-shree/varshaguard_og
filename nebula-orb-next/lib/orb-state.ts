export type OrbState = 'idle' | 'connecting' | 'listening' | 'thinking' | 'speaking' | 'error' | 'disabled';
export type StateMix = { [K in OrbState]: number; update: (state: OrbState, dt: number, snap?: number) => StateMix };
export interface OrbProps {
  state?: OrbState; size?: number; speed?: number; colorFrom?: string; colorTo?: string;
  levelRef?: React.RefObject<number>; label?: string; className?: string;
  ref?: React.Ref<HTMLDivElement>;
}
export const ERROR_COLOR_FROM = '#fb7185';
export const ERROR_COLOR_TO = '#f43f5e';
export const approach = (current: number, target: number, response: number, dt: number) =>
  current + (target - current) * (1 - Math.exp(-response * dt));
export const stateEnergy = (state: OrbState, t: number): number => {
  const base: Record<OrbState, number> = { idle: .18, connecting: .24, listening: .58, thinking: .42, speaking: .7, error: .38, disabled: .08 };
  return base[state] * (.8 + .2 * Math.sin(t * (state === 'speaking' ? 7 : 3)));
};
export function createStateMix(initial: OrbState): StateMix {
  const weights = { idle: 0, connecting: 0, listening: 0, thinking: 0, speaking: 0, error: 0, disabled: 0 } as Record<OrbState, number>;
  weights[initial] = 1;
  const result = Object.assign(weights, {
    update(state: OrbState, dt: number, snap?: number) {
      const rate = snap ? 1 : Math.min(1, dt * 5);
      for (const key of Object.keys(weights) as OrbState[]) weights[key] += ((key === state ? 1 : 0) - weights[key]) * rate;
      const sum = (Object.keys(weights) as OrbState[]).reduce((total, key) => total + weights[key], 0) || 1;
      for (const key of Object.keys(weights) as OrbState[]) weights[key] /= sum;
      return result;
    },
  });
  return result;
}
