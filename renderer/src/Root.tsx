import React from "react";
import { Composition, type CalculateMetadataFunction } from "remotion";
import { Cover } from "./Cover";
import { Reel } from "./Reel";
import { sampleManifest } from "./sample";
import type { SceneManifest } from "./types";

const calculateMetadata: CalculateMetadataFunction<SceneManifest> = ({ props }) => ({
  durationInFrames: props.duration_frames,
  fps: props.fps,
  width: props.width,
  height: props.height,
});

export const Root: React.FC = () => (
  <>
  <Composition
    id="Reel"
    component={Reel}
    defaultProps={sampleManifest}
    calculateMetadata={calculateMetadata}
    durationInFrames={sampleManifest.duration_frames}
    fps={sampleManifest.fps}
    width={sampleManifest.width}
    height={sampleManifest.height}
  />
  <Composition
    id="Cover"
    component={Cover}
    defaultProps={sampleManifest}
    durationInFrames={1}
    fps={sampleManifest.fps}
    width={sampleManifest.width}
    height={sampleManifest.height}
  />
  </>
);
