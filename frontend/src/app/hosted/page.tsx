"use client";

import LandingPage from "@/components/LandingPage";

const localApp = "http://127.0.0.1:8000/";

export default function HostedLandingPage() {
  const openLocalApp = () => {
    window.location.assign(localApp);
  };

  return (
    <LandingPage
      hosted
      onLaunchApp={openLocalApp}
      onSignIn={openLocalApp}
      onSignUp={openLocalApp}
    />
  );
}
