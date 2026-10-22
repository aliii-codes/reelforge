import { Config } from "@remotion/cli/config";

// JPEG frames are much faster to capture than PNG on a 2-core CPU; the final H.264 encode
// is lossy anyway.
Config.setVideoImageFormat("jpeg");
Config.setJpegQuality(92);
Config.setOverwriteOutput(true);
Config.setChromiumOpenGlRenderer("swangle");
