export const EDITION = import.meta.env.VITE_EDITION || 'community';
export const IS_CLOUD = EDITION === 'cloud';
export const IS_COMMUNITY = EDITION !== 'cloud';
