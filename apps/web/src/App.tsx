import { Route, Routes } from "react-router-dom";
import { AuthPage } from "./pages/AuthPage";
import { Build } from "./pages/Build";
import { Explore } from "./pages/Explore";
import { Home } from "./pages/Home";
import { Library } from "./pages/Library";
import { Moderation } from "./pages/Moderation";
import { Users } from "./pages/Users";
import { Publish } from "./pages/Publish";
import { Studio } from "./pages/Studio";
import { Site } from "./runtime/Site";

export function App() {
  return (
    <Routes>
      <Route path="/" element={<Home />} />
      <Route path="/login" element={<AuthPage mode="login" />} />
      <Route path="/register" element={<AuthPage mode="register" />} />
      <Route path="/explore" element={<Explore />} />
      <Route path="/library" element={<Library />} />
      <Route path="/moderation" element={<Moderation />} />
      <Route path="/users" element={<Users />} />
      <Route path="/build/:jobId" element={<Build />} />
      <Route path="/studio/:slug" element={<Studio />} />
      <Route path="/publish/:slug" element={<Publish />} />
      <Route path="/s/:slug/*" element={<Site />} />
      <Route path="/s/:slug" element={<Site />} />
    </Routes>
  );
}
