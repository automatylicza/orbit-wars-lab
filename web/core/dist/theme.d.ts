import { Theme } from '@mui/material/styles';
/**
 * Loads the Inter font from Google Fonts CDN.
 * Call this early in your application to ensure fonts are loaded.
 * Falls back gracefully to system fonts if loading fails.
 */
export declare function loadInterFont(): void;
declare module '@mui/material/styles' {
    interface BreakpointOverrides {
        xs: true;
        sm: true;
        md: true;
        lg: true;
        xl: true;
        xs1: true;
        xs2: true;
        xs3: true;
        sm1: true;
        sm2: true;
        sm3: true;
        md1: true;
        md2: true;
        lg1: true;
        lg2: true;
        lg3: true;
        xl1: true;
        phone: true;
        tablet: true;
        desktop: true;
    }
}
declare module '@mui/material/Button' {
    interface ButtonPropsVariantOverrides {
        high: true;
        medium: true;
        low: true;
    }
}
export declare const themeBreakpoints: {
    values: {
        xs: number;
        xs1: number;
        xs2: number;
        xs3: number;
        sm: number;
        sm1: number;
        sm2: number;
        sm3: number;
        md: number;
        md1: number;
        md2: number;
        lg: number;
        lg1: number;
        lg2: number;
        lg3: number;
        xl: number;
        xl1: number;
        phone: number;
        tablet: number;
        desktop: number;
    };
};
export declare const theme: Theme;
export declare const lightTheme: Theme;
