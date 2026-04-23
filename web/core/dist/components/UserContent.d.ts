import * as React from 'react';
export interface UserContentProps {
    markdown: string;
    style?: React.CSSProperties;
    className?: string;
}
export declare const UserContent: React.ForwardRefExoticComponent<UserContentProps & React.RefAttributes<HTMLDivElement>>;
