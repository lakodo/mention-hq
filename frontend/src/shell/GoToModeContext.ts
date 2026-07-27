import { createContext, useContext } from 'react';

/** True while the `g` "go to" prefix is armed, so the nav tabs can show their key badges. */
export const GoToModeContext = createContext(false);

export const useGoToMode = () => useContext(GoToModeContext);
