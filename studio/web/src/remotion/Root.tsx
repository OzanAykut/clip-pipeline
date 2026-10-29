import React from 'react';
import { Composition } from 'remotion';
import { Main, type MainProps } from './Main';
import { projectDuration } from '../types';

// Disa aktarma (Node render) icin kok. Sure/boyut inputProps'taki projeden hesaplanir.
export const Root: React.FC = () => (
  <Composition
    id="Main"
    component={Main as unknown as React.FC<Record<string, unknown>>}
    width={1080}
    height={1920}
    fps={30}
    durationInFrames={30}
    defaultProps={{} as Record<string, unknown>}
    calculateMetadata={({ props }) => {
      const { project } = props as unknown as MainProps;
      return {
        durationInFrames: Math.max(1, Math.round(projectDuration(project) * project.fps)),
        fps: project.fps, width: project.width, height: project.height,
      };
    }}
  />
);
